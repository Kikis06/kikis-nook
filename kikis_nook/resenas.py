"""
resenas.py - Reseñas y calificaciones de Kiki's Nook

Modelo en Redis:
    resenas:{id_libro}     List  -> reseñas en JSON, la más nueva primero (máx. 50)
    libro:{id_libro}       Hash  -> campos calif_suma y calif_total
    ranking:calificacion   ZSet  -> {id_libro: promedio de estrellas}
"""
import json
from datetime import date

from kikis_nook.conexion import obtener_conexion

MAX_RESENAS = 50  # solo guardamos las 50 más recientes por libro


def agregar_resena(id_libro: str, usuario: str, estrellas: int, texto: str) -> bool:
    r = obtener_conexion()
    estrellas = int(estrellas)
    if not r.exists(f"libro:{id_libro}") or not 1 <= estrellas <= 5:
        return False

    resena = json.dumps({"usuario": usuario, "estrellas": estrellas, "texto": texto,
                         "fecha": date.today().isoformat()}, ensure_ascii=False)
    pipe = r.pipeline()
    pipe.lpush(f"resenas:{id_libro}", resena)
    pipe.ltrim(f"resenas:{id_libro}", 0, MAX_RESENAS - 1)  # lista con tope
    pipe.hincrby(f"libro:{id_libro}", "calif_suma", estrellas)
    pipe.hincrby(f"libro:{id_libro}", "calif_total", 1)
    _, _, suma, total = pipe.execute()

    r.zadd("ranking:calificacion", {id_libro: round(suma / total, 2)})
    return True


def ver_resenas(id_libro: str, cuantas: int = 10) -> list:
    """Las reseñas más recientes de un libro (LRANGE)."""
    crudas = obtener_conexion().lrange(f"resenas:{id_libro}", 0, cuantas - 1)
    return [json.loads(x) for x in crudas]


def mejor_calificados(n: int = 5) -> list:
    """Top n por promedio de estrellas: [(id_libro, promedio), ...]."""
    return obtener_conexion().zrevrange("ranking:calificacion", 0, n - 1, withscores=True)


if __name__ == "__main__":
    # Prueba rápida:  python -m kikis_nook.resenas
    agregar_resena("kn003", "kiki", 5, "Releído y me gustó todavía más.")
    for x in ver_resenas("kn003"):
        print(f"  {'★' * x['estrellas']}  {x['usuario']}: {x['texto']}")
    print("Mejor calificados:", mejor_calificados(3))