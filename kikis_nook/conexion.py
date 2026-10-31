"""
conexion.py
Crea y comparte una única conexión a Redis (Upstash) para todo el proyecto.
Las credenciales se leen de variables de entorno (.env), nunca del código.
"""
import os
import redis
from dotenv import load_dotenv

load_dotenv()

_cliente = None  # aquí guardamos la conexión para reutilizarla


def obtener_conexion() -> redis.Redis:
    """Devuelve el cliente de Redis. Lo crea solo la primera vez."""
    global _cliente
    if _cliente is None:
        _cliente = redis.Redis(
            host=os.getenv("REDIS_HOST"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            username=os.getenv("REDIS_USERNAME", "default"),
            password=os.getenv("REDIS_PASSWORD"),
            ssl=True,               # Upstash exige conexión cifrada (TLS)
            decode_responses=True,  # respuestas como str, no bytes
        )
    return _cliente


if __name__ == "__main__":
    # Prueba rápida:  python -m kikis_nook.conexion
    r = obtener_conexion()
    print("Conectado a Kiki's Nook ☕📚:", r.ping())