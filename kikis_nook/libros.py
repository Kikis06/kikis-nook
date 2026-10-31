"""
libros.py - CRUD del catálogo de Kiki's Nook

Modelo en Redis:
    libro:{id}        Hash  -> datos del libro
    libros:todos      Set   -> ids de todos los libros
    genero:{nombre}   Set   -> ids de los libros de ese género
    libros:generos    Set   -> nombres de los géneros existentes
    contador:libros   String-> último número de id usado (INCR)
"""
from kikis_nook.conexion import obtener_conexion

# Campos que se permiten editar desde la app
CAMPOS_EDITABLES = {"titulo", "autor", "anio", "precio", "stock", "generos"}


# ---------------------------------------------------------------------------
# Funciones de apoyo
# ---------------------------------------------------------------------------
def _clave(id_libro: str) -> str:
    """Arma la clave del Hash de un libro. Ej: 'kn001' -> 'libro:kn001'."""
    return f"libro:{id_libro}"


def _a_lista(generos) -> list:
    """Acepta 'fantasia, romance' o ['fantasia','romance'] y devuelve una lista limpia."""
    if isinstance(generos, str):
        generos = generos.split(",")
    return [g.strip().lower() for g in generos if g.strip()]


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------
def crear_libro(titulo, autor, anio, precio, stock, generos) -> str:
    """Crea un libro nuevo y devuelve su id (ej. 'kn011')."""
    r = obtener_conexion()
    # INCR es atómico: aunque dos personas creen libros a la vez, nunca se repite el id
    numero = r.incr("contador:libros")
    id_libro = f"kn{numero:03d}"
    lista_generos = _a_lista(generos)

    pipe = r.pipeline()  # MULTI/EXEC: o se guarda todo, o nada
    pipe.hset(_clave(id_libro), mapping={
        "id": id_libro,
        "titulo": titulo,
        "autor": autor,
        "anio": int(anio),
        "precio": float(precio),
        "stock": int(stock),
        "generos": ",".join(lista_generos),
        "calif_suma": 0,
        "calif_total": 0,
    })
    pipe.sadd("libros:todos", id_libro)
    for g in lista_generos:
        pipe.sadd(f"genero:{g}", id_libro)
        pipe.sadd("libros:generos", g)
    pipe.execute()
    return id_libro


# ---------------------------------------------------------------------------
# READ
# ---------------------------------------------------------------------------
def obtener_libro(id_libro: str):
    """Devuelve un dict con los datos del libro, o None si no existe."""
    r = obtener_conexion()
    libro = r.hgetall(_clave(id_libro))
    if not libro:
        return None
    libro["generos"] = _a_lista(libro.get("generos", ""))
    # Si hay oferta relámpago vigente, la agregamos (si ya expiró, Redis la borró solo)
    oferta = r.get(f"oferta:{id_libro}")
    libro["oferta"] = float(oferta) if oferta else None
    total = int(libro.get("calif_total", 0))
    libro["calificacion"] = round(int(libro.get("calif_suma", 0)) / total, 1) if total else None
    return libro


def listar_libros(genero: str = None) -> list:
    """Lista todo el catálogo o solo un género, ordenado por título."""
    r = obtener_conexion()
    origen = f"genero:{genero}" if genero else "libros:todos"
    ids = r.smembers(origen)
    libros = [obtener_libro(i) for i in ids]
    return sorted([l for l in libros if l], key=lambda l: l["titulo"])


def libros_en_generos(*generos) -> list:
    """Libros que están en TODOS los géneros indicados (intersección SINTER)."""
    r = obtener_conexion()
    ids = r.sinter([f"genero:{g}" for g in generos])
    return [obtener_libro(i) for i in ids]


def listar_generos() -> list:
    """Nombres de todos los géneros, en orden alfabético."""
    return sorted(obtener_conexion().smembers("libros:generos"))


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------
def actualizar_libro(id_libro: str, **cambios) -> bool:
    """Actualiza solo los campos enviados. Ej: actualizar_libro('kn001', precio=459)."""
    r = obtener_conexion()
    if not r.exists(_clave(id_libro)):
        return False

    cambios = {k: v for k, v in cambios.items() if k in CAMPOS_EDITABLES}
    pipe = r.pipeline()

    # Si cambian los géneros, también hay que mover el id entre los Sets
    if "generos" in cambios:
        viejos = set(_a_lista(r.hget(_clave(id_libro), "generos") or ""))
        nuevos = set(_a_lista(cambios["generos"]))
        for g in viejos - nuevos:
            pipe.srem(f"genero:{g}", id_libro)
        for g in nuevos - viejos:
            pipe.sadd(f"genero:{g}", id_libro)
            pipe.sadd("libros:generos", g)
        cambios["generos"] = ",".join(sorted(nuevos))

    if cambios:
        pipe.hset(_clave(id_libro), mapping=cambios)
    pipe.execute()
    return True


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------
def eliminar_libro(id_libro: str) -> bool:
    """Borra el libro y TODAS sus referencias (Sets, rankings, reseñas, oferta)."""
    r = obtener_conexion()
    generos = r.hget(_clave(id_libro), "generos")
    if generos is None:
        return False

    pipe = r.pipeline()  # transacción: no quedan referencias "huérfanas"
    pipe.delete(_clave(id_libro))
    pipe.srem("libros:todos", id_libro)
    for g in _a_lista(generos):
        pipe.srem(f"genero:{g}", id_libro)
    pipe.zrem("ranking:vendidos", id_libro)
    pipe.zrem("ranking:calificacion", id_libro)
    pipe.delete(f"resenas:{id_libro}", f"oferta:{id_libro}")
    pipe.execute()
    return True


# ---------------------------------------------------------------------------
# Prueba rápida del CRUD:  python -m kikis_nook.libros
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("1) CREATE")
    nuevo = crear_libro("Libro de prueba", "Kiki", 2026, 199, 3, "fantasia, juvenil")
    print("   Creado:", nuevo)

    print("2) READ")
    print("  ", obtener_libro(nuevo))
    print("   Distopía + juvenil:", [l["titulo"] for l in libros_en_generos("distopia", "juvenil")])

    print("3) UPDATE")
    actualizar_libro(nuevo, precio=149, generos="romance")
    print("  ", obtener_libro(nuevo))

    print("4) DELETE")
    print("   Eliminado:", eliminar_libro(nuevo))
    print("   ¿Sigue existiendo?:", obtener_libro(nuevo))