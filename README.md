# Seguimiento de jugadores

Proyecto independiente y autocontenido: seguimiento de jugadores de
baloncesto centrado en la ficha individual de cada jugador — trayectoria
de equipos, estadísticas por temporada, diario de lesiones, datos
económicos y otros hitos de carrera. No depende de ninguna otra base de
datos ni proyecto.

## Estructura

```
seguimiento_jugadores/
├── config.py               # Rutas centrales (BD, esquema)
├── database/
│   ├── schema.sql           # Definición de todas las tablas y catálogos
│   └── init_db.py           # Script de inicialización de la BD
├── db/
│   └── conexion.py           # Conexión + helpers de catálogo/equipos
├── scraping/                 # Scraper de estadísticas/trayectoria (acb.com)
│   ├── base_scraper.py        # Sesión HTTP, reintentos, parseo genérico de tablas
│   ├── estadisticas.py        # Tabla de temporadas de acb.com
│   ├── trayectoria.py         # Historial de equipos de acb.com
│   └── actualizar_jugador.py  # Orquesta ambos para un jugador
├── formularios/               # App Flask de formularios manuales
│   ├── app.py                  # Fábrica de la app
│   ├── routes.py                # Jugadores, equipos, lesiones, datos económicos
│   └── templates/
├── run.py                     # Lanza la app de formularios (puerto 5500)
├── data/                       # Aquí vive el archivo .db generado (no se versiona)
└── notebooks/                  # Para EDA
```

## Puesta en marcha

```bash
pip install -r requirements.txt

python -m database.init_db          # crea data/seguimiento_jugadores.db
python -m database.init_db --reset  # la borra y la recrea desde cero

python run.py                        # arranca la app de formularios en http://127.0.0.1:5500
```

## Catálogos

Todos los campos de valores cerrados (posición, tipo de movimiento, mano dominante,
estado del jugador, fuente del dato, fiabilidad, gravedad y estado de una lesión,
tipo de contrato) son tablas editables, no valores fijos en el esquema. Se listan o
consultan con `db.conexion.listar_catalogo(nombre_tabla)` e
`id_por_nombre(nombre_tabla, valor)`.

## Formularios manuales

La app Flask (`formularios/`) permite dar de alta equipos, jugadores, lesiones
y datos económicos con desplegables sacados de los catálogos. La ficha de cada
jugador (`/jugadores/<id>`) reúne su trayectoria, estadísticas, lesiones y datos
económicos en una sola vista.

## Scraping (fuente: acb.com)

`estadisticas.py` y `trayectoria.py` scrapean acb.com (tabla de temporadas
e historial de equipos). Verificado contra un fixture que reproduce la
página real de un jugador — pendiente de una primera ejecución con
conexión real. Uso:

```bash
python -m scraping.actualizar_jugador <jugador_id> <slug_acb>
```

Detalles y limitaciones conocidas en `scraping/README.md`.
