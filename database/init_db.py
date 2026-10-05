"""
Inicializa (o resetea) la base de datos a partir de database/schema.sql.

Uso:
    python -m database.init_db          # crea la BD si no existe
    python -m database.init_db --reset  # borra la existente y la recrea desde cero
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import DB_PATH, SCHEMA_PATH


def init_db(reset: bool = False) -> None:
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Base de datos anterior eliminada: {DB_PATH}")

    if DB_PATH.exists():
        print(f"La base de datos ya existe en {DB_PATH} (usa --reset para recrearla).")
        return

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(schema_sql)
        conn.commit()
        print(f"Base de datos creada en {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Inicializa la base de datos de seguimiento de jugadores."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Borra la base de datos existente y la recrea desde cero.",
    )
    args = parser.parse_args()
    init_db(reset=args.reset)
