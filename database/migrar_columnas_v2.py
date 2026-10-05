"""
Migración puntual: añade a estadisticas_temporada las columnas nuevas
(tiros con/int, puntos máx, rebotes ofe/def, tapones recibidos, mates,
faltas recibidas, +/-, V/D) sin borrar los datos ya existentes.

Uso (una sola vez):
    python -m database.migrar_columnas_v2
"""
import sqlite3

from config import DB_PATH

COLUMNAS_NUEVAS = [
    "puntos_max INTEGER",
    "t2_convertidos INTEGER", "t2_intentados INTEGER",
    "t3_convertidos INTEGER", "t3_intentados INTEGER",
    "tl_convertidos INTEGER", "tl_intentados INTEGER",
    "rebotes_ofensivos_totales REAL", "rebotes_defensivos_totales REAL",
    "tapones_recibidos_totales REAL",
    "mates_totales REAL",
    "faltas_recibidas_totales REAL",
    "mas_menos_promedio REAL",
    "victorias INTEGER", "derrotas INTEGER",
]


def migrar() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        existentes = {fila[1] for fila in conn.execute("PRAGMA table_info(estadisticas_temporada);")}
        añadidas = 0
        for definicion in COLUMNAS_NUEVAS:
            nombre = definicion.split()[0]
            if nombre in existentes:
                print(f"  ya existe: {nombre}")
                continue
            conn.execute(f"ALTER TABLE estadisticas_temporada ADD COLUMN {definicion};")
            print(f"  añadida: {definicion}")
            añadidas += 1
        conn.commit()
        print(f"\nMigración completada ({añadidas} columnas nuevas).")
    finally:
        conn.close()


if __name__ == "__main__":
    migrar()
