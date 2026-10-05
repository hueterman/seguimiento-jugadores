"""
Configuración central del proyecto de seguimiento de jugadores.
Cualquier script (inicialización, scraper, formularios) importa las rutas desde aquí.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "seguimiento_jugadores.db"
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"
