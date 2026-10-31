"""
extras.py - Funciones especiales de Kiki's Nook (la mayoría usan TTL)

Modelo en Redis:
    oferta:{id_libro}            String -> precio de oferta          TTL variable
    sorpresa:hoy                 String -> id del libro sorpresa     TTL 24 h
    apartado:{usuario}:{id}      Hash   -> datos del apartado        TTL 48 h
    historial:{usuario}          List   -> últimos 10 libros vistos
    ranking:vendidos             ZSet   -> {id_libro: ventas}
    ventas:{fecha}               String -> libros vendidos ese día
"""
from datetime import date, datetime

from kikis_nook.conexion import obtener_conexion
from kikis_nook.libros import obtener_libro

TTL_SORPRESA = 24 * 60 * 60
TTL_APARTADO = 48 * 60 * 60
MAX_HISTORIAL = 10


def formato_tiempo(segundos) -> str:
    """Convierte segundos a algo legible. Ej: 5430 -> '1 h 30 min'."""
    if segundos is None or segundos < 0:
        return "sin límite"
    h, resto = divmod(int(segundos), 3600)
    m = resto // 60
    return f"{h} h {m} min" if h else f"{m} min"


# ---------------------------------------------------------------------------
# Ofertas relámpago (String + TTL)
# ---------------------------------------------------------------------------
def crear_oferta(id_libro: str, precio_oferta: float, minutos: int) -> bool:
    r = obtener_conexion()
    if not r.exists(f"libro:{id_libro}"):
        return False
    r.set(f"oferta:{id_libro}", precio_oferta, ex=int(minutos) * 60)
    return True


def ofertas_activas() -> list:
    """Recorre las ofertas vigentes con SCAN y agrega el tiempo que les queda."""
    r = obtener_conexion()
    ofertas = []
    for clave in r.scan_iter(match="oferta:*"):
        id_libro = clave.split(":", 1)[1]
        libro = obtener_libro(id_libro)
        if libro and libro["oferta"] is not None:
            libro["oferta_expira"] = formato_tiempo(r.ttl(clave))
            ofertas.append(libro)
    return ofertas


# ---------------------------------------------------------------------------
# Libro sorpresa del día (String + TTL 24 h)
# ---------------------------------------------------------------------------
def obtener_sorpresa():
    """
    Si la sorpresa ya expiró, Redis la borró sola; entonces elegimos otro libro
    al azar (SRANDMEMBER) y lo guardamos con 24 h de vida.
    """
    r = obtener_conexion()
    id_libro = r.get("sorpresa:hoy")
    if id_libro is None:
        id_libro = r.srandmember("libros:todos")
        if id_libro is None:
            return None
        # NX: solo la guarda si nadie más la creó al mismo tiempo
        r.set("sorpresa:hoy", id_libro, ex=TTL_SORPRESA, nx=True)
        id_libro = r.get("sorpresa:hoy")
    libro = obtener_libro(id_libro)
    if libro:
        libro["sorpresa_expira"] = formato_tiempo(r.ttl("sorpresa:hoy"))
    return libro


# ---------------------------------------------------------------------------
# Apartados que expiran en 48 h (Hash + TTL)
# ---------------------------------------------------------------------------
def apartar_libro(usuario: str, id_libro: str):
    """Aparta un libro por 48 h. Devuelve (True, mensaje) o (False, motivo)."""
    r = obtener_conexion()
    libro = obtener_libro(id_libro)
    if not libro:
        return False, "Ese libro no existe."
    if int(libro["stock"]) <= 0:
        return False, "Lo sentimos, ya no hay ejemplares."
    clave = f"apartado:{usuario}:{id_libro}"
    if r.exists(clave):
        return False, "Ya tienes apartado este libro."
    pipe = r.pipeline()
    pipe.hset(clave, mapping={"usuario": usuario, "id_libro": id_libro,
                              "titulo": libro["titulo"],
                              "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")})
    pipe.expire(clave, TTL_APARTADO)
    pipe.execute()
    return True, f"«{libro['titulo']}» apartado por 48 horas."


def mis_apartados(usuario: str) -> list:
    r = obtener_conexion()
    resultado = []
    for clave in r.scan_iter(match=f"apartado:{usuario}:*"):
        datos = r.hgetall(clave)
        if datos:
            datos["expira"] = formato_tiempo(r.ttl(clave))
            resultado.append(datos)
    return resultado


def cancelar_apartado(usuario: str, id_libro: str) -> bool:
    return obtener_conexion().delete(f"apartado:{usuario}:{id_libro}") == 1


# ---------------------------------------------------------------------------
# Historial "vistos recientemente" (List con tope)
# ---------------------------------------------------------------------------
def registrar_vista(usuario: str, id_libro: str) -> None:
    clave = f"historial:{usuario}"
    pipe = obtener_conexion().pipeline()
    pipe.lrem(clave, 0, id_libro)              # si ya estaba, lo quitamos
    pipe.lpush(clave, id_libro)                # y lo ponemos al inicio
    pipe.ltrim(clave, 0, MAX_HISTORIAL - 1)    # solo los últimos 10
    pipe.execute()


def ver_historial(usuario: str) -> list:
    ids = obtener_conexion().lrange(f"historial:{usuario}", 0, -1)
    return [l for l in (obtener_libro(i) for i in ids) if l]


# ---------------------------------------------------------------------------
# Estadísticas (Sorted Set y contadores)
# ---------------------------------------------------------------------------
def mas_vendidos(n: int = 5) -> list:
    """Top n por ventas: [(libro, ventas), ...] usando ZREVRANGE."""
    top = obtener_conexion().zrevrange("ranking:vendidos", 0, n - 1, withscores=True)
    return [(obtener_libro(i), int(v)) for i, v in top]


def ventas_de_hoy() -> int:
    return int(obtener_conexion().get(f"ventas:{date.today().isoformat()}") or 0)


if __name__ == "__main__":
    # Prueba rápida:  python -m kikis_nook.extras
    s = obtener_sorpresa()
    print("Sorpresa del día:", s["titulo"], "| cambia en", s["sorpresa_expira"])
    crear_oferta("kn004", 279, 30)
    print("Ofertas:", [(o["titulo"], o["oferta"], o["oferta_expira"]) for o in ofertas_activas()])
    print(apartar_libro("kiki", "kn002"))
    print(apartar_libro("kiki", "kn002"))  # el segundo debe fallar
    print("Mis apartados:", mis_apartados("kiki"))
    for i in ["kn001", "kn005", "kn001"]:
        registrar_vista("kiki", i)
    print("Historial:", [l["titulo"] for l in ver_historial("kiki")])
    print("Más vendidos:", [(l["titulo"], v) for l, v in mas_vendidos(3)])
    print("Libros vendidos hoy:", ventas_de_hoy())