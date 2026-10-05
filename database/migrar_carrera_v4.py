"""
Migración puntual: crea la tabla estadisticas_carrera (totales/promedios
reales de carrera que publica acb.com) si todavía no existe.

Uso (una sola vez):
    python -m database.migrar_carrera_v4
"""
import sqlite3

from config import DB_PATH

SQL_TABLA = """
CREATE TABLE estadisticas_carrera (
    id                      INTEGER PRIMARY KEY,
    jugador_id              INTEGER NOT NULL REFERENCES jugadores(id) ON DELETE CASCADE,
    competicion             TEXT,
    tipo_fila               TEXT NOT NULL,
    partidos_jugados        REAL,
    partidos_titular        REAL,
    minutos                 REAL,
    puntos                  REAL,
    puntos_max              REAL,
    t2_convertidos          REAL,
    t2_intentados           REAL,
    porcentaje_tiro2        REAL,
    t3_convertidos          REAL,
    t3_intentados           REAL,
    porcentaje_tiro3        REAL,
    tl_convertidos          REAL,
    tl_intentados           REAL,
    porcentaje_tiro_libre   REAL,
    rebotes_ofensivos       REAL,
    rebotes_defensivos      REAL,
    rebotes                 REAL,
    asistencias             REAL,
    robos                   REAL,
    tapones_favor           REAL,
    tapones_contra          REAL,
    mates                   REAL,
    perdidas                REAL,
    faltas_cometidas        REAL,
    faltas_recibidas        REAL,
    mas_menos                REAL,
    valoracion_pir           REAL,
    victorias                REAL,
    derrotas                 REAL,
    fuente_id                INTEGER NOT NULL DEFAULT 1 REFERENCES fuentes(id),
    fecha_actualizacion      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (jugador_id, competicion, tipo_fila)
);
"""


def migrar() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        existe = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='estadisticas_carrera';"
        ).fetchone()
        if existe:
            print("La tabla estadisticas_carrera ya existía. Nada que hacer.")
            return
        conn.execute(SQL_TABLA)
        conn.execute("CREATE INDEX idx_carrera_jugador ON estadisticas_carrera(jugador_id);")
        conn.commit()
        print("Tabla estadisticas_carrera creada.")
    finally:
        conn.close()


if __name__ == "__main__":
    migrar()
