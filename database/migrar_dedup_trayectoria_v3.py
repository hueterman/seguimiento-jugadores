"""
Migración puntual: elimina filas duplicadas en trayectoria (mismo
jugador/equipo/temporada) y añade el índice único que evita que vuelva a
pasar al re-ejecutar el scraper.

Uso (una sola vez):
    python -m database.migrar_dedup_trayectoria_v3
"""
import sqlite3

from config import DB_PATH


def migrar() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        duplicados = conn.execute(
            """
            SELECT jugador_id, equipo_id, temporada, COUNT(*) AS n
            FROM trayectoria
            GROUP BY jugador_id, equipo_id, temporada
            HAVING COUNT(*) > 1;
            """
        ).fetchall()

        if duplicados:
            print(f"Grupos duplicados encontrados: {len(duplicados)}")
            borradas = conn.execute(
                """
                DELETE FROM trayectoria
                WHERE id NOT IN (
                    SELECT MIN(id)
                    FROM trayectoria
                    GROUP BY jugador_id, equipo_id, temporada
                );
                """
            ).rowcount
            print(f"  filas duplicadas eliminadas: {borradas}")
        else:
            print("No había filas duplicadas en trayectoria.")

        indices = {fila[1] for fila in conn.execute("PRAGMA index_list(trayectoria);")}
        if "idx_trayectoria_unica" not in indices:
            conn.execute(
                "CREATE UNIQUE INDEX idx_trayectoria_unica "
                "ON trayectoria(jugador_id, equipo_id, temporada);"
            )
            print("Índice único idx_trayectoria_unica creado.")
        else:
            print("El índice único ya existía.")

        conn.commit()
        print("\nMigración completada.")
    finally:
        conn.close()


if __name__ == "__main__":
    migrar()
