# ☕ Kiki's Nook — café librería en la nube

Aplicación web de una librería en línea cuya base de datos es **Redis (modelo clave-valor)** alojado en la nube con **Upstash**. Está hecha en **Python** con el SDK oficial **redis-py** y el framework web **Flask**.

Proyecto del segundo parcial de **Bases de Datos Avanzadas**.

## Funcionalidades

- **CRUD completo de libros** desde el panel de administración: crear, leer, actualizar y eliminar.
- **Catálogo filtrado por género**, con índices hechos con Sets.
- **Carrito de compras con TTL de 30 minutos** (expiración deslizante) y compra con transacción `WATCH`/`MULTI`/`EXEC`.
- **Apartados que expiran a las 48 horas.**
- **Ofertas relámpago** con duración definida por el administrador.
- **Libro sorpresa del día**, que cambia solo cada 24 horas.
- **Reseñas y calificaciones**, con promedio precalculado.
- **Rankings** de más vendidos y mejor calificados (Sorted Sets).
- **Historial** de libros vistos recientemente.

## Requerimientos

- Python 3.10 o superior
- Git
- Una base de datos Redis en la nube. Este proyecto usa [Upstash](https://upstash.com), con el plan gratuito.

Las librerías de Python están en `requirements.txt`: `redis`, `flask` y `python-dotenv`, entre otras.

## Instalación

1. **Clona el repositorio**
   ```bash
   git clone https://github.com/Kikis06/kikis-nook.git
   cd kikis-nook
   ```

2. **Crea y activa un entorno virtual**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Mac / Linux
   source venv/bin/activate
   ```

3. **Instala las dependencias**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configura las credenciales.** Copia `.env.example` a un archivo nuevo llamado `.env` y llénalo con los datos de tu base en Upstash (pestaña *Details*: Endpoint, Port y Token):
   ```
   REDIS_HOST=tu-base.upstash.io
   REDIS_PORT=6379
   REDIS_USERNAME=default
   REDIS_PASSWORD=tu_token_de_upstash
   FLASK_SECRET_KEY=cualquier_texto_largo_y_secreto
   ```
   > ⚠️ El archivo `.env` **nunca** se sube al repositorio; está excluido en `.gitignore`.

5. **Prueba la conexión a la nube**
   ```bash
   python -m kikis_nook.conexion
   ```
   Debe imprimir `Conectado a Kiki's Nook ☕📚: True`.

## Ejecución

1. **Carga los datos iniciales (seeding).** Limpia las claves del proyecto y carga 10 libros, 8 géneros, reseñas, rankings, una oferta y el libro sorpresa:
   ```bash
   python seed.py
   ```

2. **Inicia la aplicación web**
   ```bash
   python app.py
   ```

3. Abre **http://127.0.0.1:5000** en el navegador.

Cada módulo también se puede probar por separado:
```bash
python -m kikis_nook.libros     # CRUD
python -m kikis_nook.carrito    # carrito y compra
python -m kikis_nook.resenas    # reseñas y calificaciones
python -m kikis_nook.extras     # ofertas, sorpresa, apartados, historial
```

## Estructura del proyecto

```
kikis-nook/
├── kikis_nook/            # Lógica de negocio (habla con Redis)
│   ├── __init__.py
│   ├── conexion.py        # Cliente redis-py único, TLS, credenciales por .env
│   ├── libros.py          # CRUD de libros e índices por género
│   ├── carrito.py         # Carrito con TTL y compra con WATCH
│   ├── resenas.py         # Reseñas (List) y ranking de calificación
│   └── extras.py          # Ofertas, sorpresa del día, apartados, historial, ventas
├── templates/             # Páginas HTML (Jinja)
├── static/estilos.css     # Diseño de la página
├── app.py                 # Servidor web Flask (rutas)
├── seed.py                # Script de datos iniciales
├── requirements.txt
├── .env.example           # Plantilla de credenciales (sin datos reales)
└── .gitignore
```

## Arquitectura

```
Navegador ──HTTP──► Flask (app.py) ──► kikis_nook/*.py ──redis-py + TLS──► Upstash Redis (nube)
```

La aplicación corre en la computadora local; **todos los datos viven en Upstash**. La conexión va cifrada con TLS (puerto 6379) y se autentica con usuario y token.

## Modelo de datos (resumen)

| Clave | Tipo | TTL |
|---|---|---|
| `libro:{id}` | Hash | — |
| `libros:todos` | Set | — |
| `genero:{nombre}` | Set | — |
| `ranking:vendidos` | Sorted Set | — |
| `ranking:calificacion` | Sorted Set | — |
| `resenas:{id}` | List (JSON) | — |
| `historial:{usuario}` | List | — |
| `ventas:{fecha}` | String (contador) | — |
| `carrito:{usuario}` | Hash | 30 min |
| `apartado:{usuario}:{id}` | Hash | 48 h |
| `oferta:{id}` | String | variable |
| `sorpresa:hoy` | String | 24 h |

El diseño completo, la justificación frente a SQL y el catálogo de consultas están en el documento PDF del proyecto.

## Autora

[Tu nombre] · Bases de Datos Avanzadas · [Grupo]
