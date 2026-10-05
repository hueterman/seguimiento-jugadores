"""
Migración puntual: añade la columna jugadores.id_externo_euroleague.

Por qué una columna nueva y no reutilizar id_externo_acb: un jugador que
juega ACB y Euroliga/EuroCup la misma temporada es UNA sola fila en
"jugadores" (se identifica por nombre+apellidos, no por equipo/competición -
ver db.conexion.buscar_o_crear_jugador). Si guardáramos el id de Euroliga en
id_externo_acb, pisaríamos el id de acb.com de ese mismo jugador. Con una
columna separada, cada fuente guarda su propio id sin chocar.

Uso (una sola vez):
    python -m database.migrar_euroleague_v6
"""
import sqlite3

from config import DB_PATH


def _columna_existe(conn: sqlite3.Connection, tabla: str, columna: str) -> bool:
    filas = conn.execute(f"PRAGMA table_info({tabla});").fetchall()
    return any(fila[1] == columna for fila in filas)


def migrar() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        if _columna_existe(conn, "jugadores", "id_externo_euroleague"):
            print("La columna jugadores.id_externo_euroleague ya existía. Nada que hacer.")
            return
        conn.execute("ALTER TABLE jugadores ADD COLUMN id_externo_euroleague TEXT;")
        conn.commit()
        print("Columna jugadores.id_externo_euroleague añadida.")
    finally:
        conn.close()


if __name__ == "__main__":
    migrar()
