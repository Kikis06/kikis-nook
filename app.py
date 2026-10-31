"""
app.py - Servidor web de Kiki's Nook (Flask)

Ejecutar:
    python app.py
y abrir http://127.0.0.1:5000 en el navegador.

La app corre en tu compu, pero TODOS los datos se leen y escriben
en Redis (Upstash) en la nube a través de los módulos de kikis_nook.
"""
import os
import time

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, session, url_for

from kikis_nook import carrito, extras, libros, resenas
from kikis_nook.conexion import obtener_conexion

load_dotenv()

app = Flask(__name__)
# La clave secreta firma la cookie de sesión (quién es el usuario)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "solo-para-desarrollo")


def usuario_actual() -> str:
    return session.get("usuario", "invitado")


@app.template_filter("tono")
def tono_portada(id_libro: str) -> int:
    """Elige uno de 6 colores de portada a partir del id (kn001 -> 1, ...)."""
    digitos = "".join(c for c in str(id_libro) if c.isdigit()) or "0"
    return int(digitos) % 6


@app.template_filter("dinero")
def dinero(valor) -> str:
    return f"${float(valor):,.0f}"


@app.context_processor
def datos_globales():
    """Datos disponibles en TODAS las páginas: usuario, carrito y estado de la nube."""
    r = obtener_conexion()
    inicio = time.perf_counter()
    r.ping()
    latencia = (time.perf_counter() - inicio) * 1000
    piezas = sum(int(c) for c in r.hvals(f"carrito:{usuario_actual()}"))
    return {"usuario": usuario_actual(), "piezas_carrito": piezas,
            "latencia_ms": round(latencia)}


# ---------------------------------------------------------------------------
# Páginas para clientes
# ---------------------------------------------------------------------------
@app.route("/")
def inicio():
    genero = request.args.get("genero")
    return render_template(
        "inicio.html",
        catalogo=libros.listar_libros(genero),
        generos=libros.listar_generos(),
        genero_actual=genero,
        sorpresa=extras.obtener_sorpresa(),
        ofertas=extras.ofertas_activas(),
        top=extras.mas_vendidos(5),
    )


@app.route("/libro/<id_libro>")
def ver_libro(id_libro):
    libro = libros.obtener_libro(id_libro)
    if not libro:
        flash("Ese libro no existe 😢", "error")
        return redirect(url_for("inicio"))
    extras.registrar_vista(usuario_actual(), id_libro)
    return render_template("libro.html", libro=libro,
                           resenas=resenas.ver_resenas(id_libro))


@app.post("/libro/<id_libro>/resena")
def nueva_resena(id_libro):
    ok = resenas.agregar_resena(id_libro, usuario_actual(),
                                request.form.get("estrellas", 5),
                                request.form.get("texto", "").strip())
    flash("¡Gracias por tu reseña! ☕" if ok else "No se pudo guardar la reseña.",
          "ok" if ok else "error")
    return redirect(url_for("ver_libro", id_libro=id_libro))


@app.post("/libro/<id_libro>/apartar")
def apartar(id_libro):
    ok, mensaje = extras.apartar_libro(usuario_actual(), id_libro)
    flash(mensaje, "ok" if ok else "error")
    return redirect(url_for("ver_libro", id_libro=id_libro))


@app.post("/carrito/agregar/<id_libro>")
def agregar_carrito(id_libro):
    carrito.agregar_al_carrito(usuario_actual(), id_libro,
                               int(request.form.get("cantidad", 1)))
    flash("Agregado a tu carrito 🛒", "ok")
    return redirect(request.referrer or url_for("inicio"))


@app.route("/carrito")
def ver_carrito():
    return render_template("carrito.html", c=carrito.ver_carrito(usuario_actual()))


@app.post("/carrito/quitar/<id_libro>")
def quitar_carrito(id_libro):
    carrito.quitar_del_carrito(usuario_actual(), id_libro)
    return redirect(url_for("ver_carrito"))


@app.post("/carrito/comprar")
def comprar():
    ok, resultado = carrito.comprar(usuario_actual())
    if ok:
        flash(f"¡Compra realizada por {dinero(resultado)}! Gracias por leer con nosotras 💌", "ok")
        return redirect(url_for("inicio"))
    flash(resultado, "error")
    return redirect(url_for("ver_carrito"))


@app.route("/mi-rincon")
def mi_rincon():
    u = usuario_actual()
    return render_template("mi_rincon.html", apartados=extras.mis_apartados(u),
                           historial=extras.ver_historial(u))


@app.post("/apartado/cancelar/<id_libro>")
def cancelar_apartado(id_libro):
    extras.cancelar_apartado(usuario_actual(), id_libro)
    flash("Apartado cancelado.", "ok")
    return redirect(url_for("mi_rincon"))


@app.post("/entrar")
def entrar():
    nombre = request.form.get("nombre", "").strip().lower()
    session["usuario"] = nombre or "invitado"
    return redirect(request.referrer or url_for("inicio"))


# ---------------------------------------------------------------------------
# Panel de administración (CRUD de libros y ofertas)
# ---------------------------------------------------------------------------
@app.route("/admin")
def admin():
    return render_template("admin.html", catalogo=libros.listar_libros(),
                           ofertas=extras.ofertas_activas(),
                           vendidos_hoy=extras.ventas_de_hoy(), libro=None)


@app.post("/admin/crear")
def admin_crear():
    f = request.form
    nuevo = libros.crear_libro(f["titulo"], f["autor"], f["anio"], f["precio"],
                               f["stock"], f["generos"], f.get("sinopsis", ""),
                               f.get("portada", ""))
    flash(f"Libro creado con id {nuevo} ✨", "ok")
    return redirect(url_for("admin"))


@app.route("/admin/editar/<id_libro>", methods=["GET", "POST"])
def admin_editar(id_libro):
    if request.method == "POST":
        cambios = {k: v for k, v in request.form.items() if v != ""}
        libros.actualizar_libro(id_libro, **cambios)
        flash("Cambios guardados.", "ok")
        return redirect(url_for("admin"))
    return render_template("admin.html", catalogo=libros.listar_libros(),
                           ofertas=extras.ofertas_activas(),
                           vendidos_hoy=extras.ventas_de_hoy(),
                           libro=libros.obtener_libro(id_libro))


@app.post("/admin/eliminar/<id_libro>")
def admin_eliminar(id_libro):
    libros.eliminar_libro(id_libro)
    flash(f"Libro {id_libro} eliminado.", "ok")
    return redirect(url_for("admin"))


@app.post("/admin/oferta")
def admin_oferta():
    f = request.form
    ok = extras.crear_oferta(f["id_libro"], float(f["precio"]), int(f["minutos"]))
    flash("Oferta relámpago creada ⚡" if ok else "No se pudo crear la oferta.",
          "ok" if ok else "error")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(debug=True)
