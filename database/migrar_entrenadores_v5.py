"""
Migración puntual: crea la tabla entrenadores (cuerpo técnico por equipo/
temporada) si todavía no existe.

Uso (una sola vez):
    python -m database.migrar_entrenadores_v5
"""
import sqlite3

from config import DB_PATH

SQL_TABLA = """
CREATE TABLE entrenadores (
    id                  INTEGER PRIMARY KEY,
    nombre              TEXT NOT NULL,
    apellidos           TEXT NOT NULL,
    cargo               TEXT,
    equipo_id           INTEGER REFERENCES equipos(id),
    temporada           TEXT,
    id_externo_acb      TEXT,
    fuente_id           INTEGER NOT NULL DEFAULT 1 REFERENCES fuentes(id),
    fecha_registro      TEXT NOT NULL DEFAULT (datetime('now')),
    fecha_actualizacion TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (nombre, apellidos, equipo_id, temporada)
);
"""


def migrar() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        existe = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='entrenadores';"
        ).fetchone()
        if existe:
            print("La tabla entrenadores ya existía. Nada que hacer.")
            return
        conn.execute(SQL_TABLA)
        conn.execute("CREATE INDEX idx_entrenadores_equipo ON entrenadores(equipo_id);")
        conn.commit()
        print("Tabla entrenadores creada.")
    finally:
        conn.close()


if __name__ == "__main__":
    migrar()
