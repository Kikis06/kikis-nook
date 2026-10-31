"""
seed.py - Datos iniciales de Kiki's Nook
-----------------------------------------
Limpia las claves del proyecto en Redis (Upstash) y vuelve a cargar
el catálogo de ejemplo, reseñas, rankings y extras con TTL.

Uso (desde la carpeta principal, con el venv activo):
    python seed.py
"""
import json
from datetime import date

from kikis_nook.conexion import obtener_conexion


# 1. DATOS DE EJEMPLO
#    id     -> identificador interno de Kiki's Nook (clave sustituta)
#    precio -> precio en MXN de nuestra librería
#    generos-> un libro puede estar en varios generos (Sets)

LIBROS = [
    {"id": "kn001", "titulo": "Alas de sangre (Fourth Wing)", "autor": "Rebecca Yarros",
     "anio": 2023, "precio": 499, "stock": 12, "generos": ["fantasia", "romance"]},
    {"id": "kn002", "titulo": "La campana de cristal", "autor": "Sylvia Plath",
     "anio": 1963, "precio": 299, "stock": 8, "generos": ["clasicos", "ficcion-literaria"]},
    {"id": "kn003", "titulo": "Lapvona", "autor": "Ottessa Moshfegh",
     "anio": 2022, "precio": 389, "stock": 5, "generos": ["ficcion-literaria"]},
    {"id": "kn004", "titulo": "Heartstopper", "autor": "Alice Oseman",
     "anio": 2019, "precio": 349, "stock": 10, "generos": ["novela-grafica", "juvenil", "romance"]},
    {"id": "kn005", "titulo": "Los juegos del hambre", "autor": "Suzanne Collins",
     "anio": 2008, "precio": 299, "stock": 15, "generos": ["distopia", "juvenil"]},
    {"id": "kn006", "titulo": "En llamas", "autor": "Suzanne Collins",
     "anio": 2009, "precio": 299, "stock": 11, "generos": ["distopia", "juvenil"]},
    {"id": "kn007", "titulo": "Sinsajo", "autor": "Suzanne Collins",
     "anio": 2010, "precio": 299, "stock": 9, "generos": ["distopia", "juvenil"]},
    {"id": "kn008", "titulo": "Balada de pájaros cantores y serpientes", "autor": "Suzanne Collins",
     "anio": 2020, "precio": 399, "stock": 7, "generos": ["distopia", "juvenil"]},
    {"id": "kn009", "titulo": "Amanecer en la cosecha", "autor": "Suzanne Collins",
     "anio": 2025, "precio": 449, "stock": 6, "generos": ["distopia", "juvenil"]},
    {"id": "kn010", "titulo": "A Certain Hunger", "autor": "Chelsea G. Summers",
     "anio": 2020, "precio": 359, "stock": 4, "generos": ["thriller", "ficcion-literaria"]},
]

# Reseñas de ejemplo: (id_libro, usuario, estrellas 1-5, texto)
RESENAS = [
    ("kn001", "kiki", 5, "No pude soltarlo, los dragones son lo máximo."),
    ("kn001", "lector42", 4, "Adictivo, aunque el romance avanza rápido."),
    ("kn002", "kiki", 5, "Duro pero hermoso. Un clásico necesario."),
    ("kn003", "lector42", 3, "Raro y perturbador, muy Moshfegh."),
    ("kn004", "kiki", 5, "Lo más tierno que he leido."),
    ("kn005", "lector42", 5, "Empieza la saga y ya no paras."),
    ("kn008", "kiki", 4, "Ver a Snow joven cambia todo."),
    ("kn010", "kiki", 4, "Oscuro, elegante y con mucha hambre."),
]

# Ventas acumuladas iniciales para el ranking de más vendidos
VENTAS_INICIALES = {
    "kn001": 48, "kn005": 41, "kn009": 37, "kn004": 30, "kn006": 26,
    "kn007": 22, "kn008": 19, "kn002": 15, "kn010": 9, "kn003": 7,
}

# Prefijos (namespaces) que pertenecen a este proyecto
PATRONES = [
    "libro:*", "libros:*", "genero:*", "ranking:*", "resenas:*",
    "carrito:*", "apartado:*", "oferta:*", "sorpresa:*",
    "historial:*", "ventas:*", "saludo",
]

# Tiempos de vida (TTL) en segundos
TTL_SORPRESA = 24 * 60 * 60  # 24 horas
TTL_OFERTA = 2 * 60 * 60     # 2 horas (oferta relámpago)



# 2. FUNCIONES DE CARGA

def limpiar(r):
    """Borra solo las claves del proyecto usando SCAN (no bloquea Redis como KEYS)."""
    borradas = 0
    for patron in PATRONES:
        for clave in r.scan_iter(match=patron, count=100):
            r.delete(clave)
            borradas += 1
    print(f"Limpieza: {borradas} claves borradas")


def cargar_libros(r):
    """Crea cada libro como Hash e indexa el catálogo y los generos en Sets."""
    pipe = r.pipeline()  # agrupa comandos en un solo viaje de red a la nube
    for libro in LIBROS:
        clave = f"libro:{libro['id']}"
        pipe.hset(clave, mapping={
            "id": libro["id"],
            "titulo": libro["titulo"],
            "autor": libro["autor"],
            "anio": libro["anio"],
            "precio": libro["precio"],
            "stock": libro["stock"],
            "generos": ",".join(libro["generos"]),
            "calif_suma": 0,
            "calif_total": 0,
        })
        pipe.sadd("libros:todos", libro["id"])
        for genero in libro["generos"]:
            pipe.sadd(f"genero:{genero}", libro["id"])
            pipe.sadd("libros:generos", genero)  # lista de géneros existentes
    pipe.execute()
    print(f"Libros: {len(LIBROS)} cargados")


def cargar_resenas(r):
    """Guarda reseñas en Lists y calcula el ranking de calificación (Sorted Set)."""
    hoy = date.today().isoformat()
    for id_libro, usuario, estrellas, texto in RESENAS:
        resena = json.dumps({"usuario": usuario, "estrellas": estrellas,
                             "texto": texto, "fecha": hoy}, ensure_ascii=False)
        r.lpush(f"resenas:{id_libro}", resena)  # la más nueva queda primero
        # HINCRBY es atómico: suma sin riesgo de que dos usuarios se pisen
        suma = r.hincrby(f"libro:{id_libro}", "calif_suma", estrellas)
        total = r.hincrby(f"libro:{id_libro}", "calif_total", 1)
        r.zadd("ranking:calificacion", {id_libro: round(suma / total, 2)})
    print(f"Reseñas: {len(RESENAS)} cargadas")


def cargar_ventas(r):
    """Inicializa el ranking de más vendidos (Sorted Set: miembro=id, score=ventas)."""
    r.zadd("ranking:vendidos", VENTAS_INICIALES)
    print("Ranking de vendidos inicializado")


def cargar_extras(r):
    """Claves temporales con TTL: libro sorpresa del día y una oferta relámpago."""
    r.set("sorpresa:hoy", "kn003", ex=TTL_SORPRESA)
    r.set("oferta:kn009", 379, ex=TTL_OFERTA)
    print("Extras: sorpresa del día (24 h) y oferta relámpago (2 h) creadas")


# 3. PROGRAMA PRINCIPAL
def main():
    r = obtener_conexion()
    print("Conectando a Kiki's Nook...", "OK" if r.ping() else "FALLO")
    limpiar(r)
    cargar_libros(r)
    cargar_resenas(r)
    cargar_ventas(r)
    cargar_extras(r)

    # Resumen para comprobar que todo quedó en la nube
    print("\n--- Resumen ---")
    print("Libros en catálogo:", r.scard("libros:todos"))
    print("Géneros:", sorted(r.smembers("libros:generos")))
    top3 = r.zrevrange("ranking:vendidos", 0, 2, withscores=True)
    print("Top 3 vendidos:", [(r.hget(f"libro:{i}", "titulo"), int(v)) for i, v in top3])
    print("Sorpresa del día expira en:", r.ttl("sorpresa:hoy"), "segundos")
    print("Oferta kn009 expira en:", r.ttl("oferta:kn009"), "segundos")


if __name__ == "__main__":
    main()