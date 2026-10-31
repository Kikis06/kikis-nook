"""
carrito.py - Carrito de compras con expiración (TTL) de Kiki's Nook

Modelo en Redis:
    carrito:{usuario}   Hash   -> {id_libro: cantidad}   TTL 30 min (se renueva con cada uso)
    ranking:vendidos    ZSet   -> {id_libro: ventas totales}
    ventas:{fecha}      String -> contador de libros vendidos ese día
"""
from datetime import date

import redis

from kikis_nook.conexion import obtener_conexion
from kikis_nook.libros import obtener_libro

TTL_CARRITO = 30 * 60  # 30 minutos


def _clave(usuario: str) -> str:
    return f"carrito:{usuario}"


def agregar_al_carrito(usuario: str, id_libro: str, cantidad: int = 1) -> bool:
    """Suma libros al carrito y reinicia su tiempo de vida a 30 minutos."""
    r = obtener_conexion()
    if not r.exists(f"libro:{id_libro}"):
        return False
    pipe = r.pipeline()
    pipe.hincrby(_clave(usuario), id_libro, int(cantidad))
    pipe.expire(_clave(usuario), TTL_CARRITO)  # expiración "deslizante"
    pipe.execute()
    return True


def quitar_del_carrito(usuario: str, id_libro: str) -> None:
    r = obtener_conexion()
    r.hdel(_clave(usuario), id_libro)
    if r.exists(_clave(usuario)):
        r.expire(_clave(usuario), TTL_CARRITO)


def vaciar_carrito(usuario: str) -> None:
    obtener_conexion().delete(_clave(usuario))


def ver_carrito(usuario: str) -> dict:
    """Devuelve los renglones del carrito, el total y cuántos segundos le quedan."""
    r = obtener_conexion()
    contenido = r.hgetall(_clave(usuario))
    renglones, total = [], 0.0
    for id_libro, cantidad in contenido.items():
        libro = obtener_libro(id_libro)
        if not libro:
            continue
        # Si hay oferta relámpago vigente, se cobra el precio de oferta
        precio = libro["oferta"] or float(libro["precio"])
        subtotal = precio * int(cantidad)
        total += subtotal
        renglones.append({"libro": libro, "cantidad": int(cantidad),
                          "precio": precio, "subtotal": subtotal})
    return {"renglones": renglones, "total": total,
            "expira_en": r.ttl(_clave(usuario)) if contenido else None}


def comprar(usuario: str):
    """
    Convierte el carrito en una compra.
    Usa WATCH (bloqueo optimista): si alguien cambia el stock de un libro
    mientras compramos, Redis cancela la transacción y la reintentamos.
    Devuelve (True, total) o (False, mensaje de error).
    """
    r = obtener_conexion()
    carrito = ver_carrito(usuario)
    if not carrito["renglones"]:
        return False, "El carrito está vacío o ya expiró."

    claves_libros = [f"libro:{x['libro']['id']}" for x in carrito["renglones"]]
    hoy = date.today().isoformat()

    with r.pipeline() as pipe:
        while True:
            try:
                pipe.watch(*claves_libros)  # "vigila" el stock de estos libros
                for x in carrito["renglones"]:
                    stock = int(pipe.hget(f"libro:{x['libro']['id']}", "stock") or 0)
                    if stock < x["cantidad"]:
                        pipe.unwatch()
                        return False, f"No hay suficiente stock de «{x['libro']['titulo']}»."

                pipe.multi()  # a partir de aquí, todo se ejecuta junto (MULTI/EXEC)
                vendidos = 0
                for x in carrito["renglones"]:
                    id_libro = x["libro"]["id"]
                    pipe.hincrby(f"libro:{id_libro}", "stock", -x["cantidad"])
                    pipe.zincrby("ranking:vendidos", x["cantidad"], id_libro)
                    vendidos += x["cantidad"]
                pipe.incrby(f"ventas:{hoy}", vendidos)
                pipe.delete(_clave(usuario))
                pipe.execute()
                return True, carrito["total"]
            except redis.WatchError:
                continue  # otro cliente modificó el stock: reintentar


if __name__ == "__main__":
    # Prueba rápida:  python -m kikis_nook.carrito
    agregar_al_carrito("kiki", "kn001")
    agregar_al_carrito("kiki", "kn009", 2)  # este tiene oferta relámpago
    c = ver_carrito("kiki")
    for x in c["renglones"]:
        print(f"  {x['cantidad']} x {x['libro']['titulo']}  ${x['subtotal']:.2f}")
    print(f"  Total: ${c['total']:.2f}   (el carrito expira en {c['expira_en']} s)")
    print("Compra:", comprar("kiki"))
    print("Stock de kn001 ahora:", obtener_libro("kn001")["stock"])
