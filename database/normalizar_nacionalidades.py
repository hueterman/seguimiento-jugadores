"""
Normalización puntual (una sola vez): pasa jugadores.nacionalidad y
equipos.pais a español, usando scraping/paises.py.

Por qué hacía falta: acb.com siempre da la nacionalidad en español
(confirmado), la API de Euroliga/EuroCup siempre la da en inglés
(confirmado), y las altas manuales antiguas por CSV se escribieron a mano
con lo que tocara en cada momento - el resultado era una mezcla de
idiomas y grafías para el mismo país (p.ej. "Croata"/"Croacia"/"Croatia").
A partir de ahora scraping/euroleague_api.py ya traduce al guardar, así
que esto es solo para lo que ya había en la BD antes de ese cambio.

Idempotente: una segunda ejecución no encuentra nada que cambiar.

Uso (una sola vez):
    python -m database.normalizar_nacionalidades
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from db.conexion import get_connection
from scraping.paises import nombre_pais_es


def normalizar() -> None:
    with get_connection() as conn:
        jugadores = conn.execute(
            "SELECT id, nacionalidad FROM jugadores WHERE nacionalidad IS NOT NULL;"
        ).fetchall()
        cambios_jugadores = 0
        for fila in jugadores:
            canonico = nombre_pais_es(fila["nacionalidad"])
            if canonico != fila["nacionalidad"]:
                conn.execute(
                    "UPDATE jugadores SET nacionalidad = ? WHERE id = ?;",
                    (canonico, fila["id"]),
                )
                print(f"  jugador id={fila['id']}: '{fila['nacionalidad']}' -> '{canonico}'")
                cambios_jugadores += 1

        equipos = conn.execute(
            "SELECT id, nombre, pais FROM equipos WHERE pais IS NOT NULL;"
        ).fetchall()
        cambios_equipos = 0
        for fila in equipos:
            canonico = nombre_pais_es(fila["pais"])
            if canonico != fila["pais"]:
                conn.execute(
                    "UPDATE equipos SET pais = ? WHERE id = ?;",
                    (canonico, fila["id"]),
                )
                print(f"  equipo '{fila['nombre']}' (id={fila['id']}): '{fila['pais']}' -> '{canonico}'")
                cambios_equipos += 1

    print(f"\n{cambios_jugadores} jugador(es) actualizados, {cambios_equipos} equipo(s) actualizados.")


if __name__ == "__main__":
    normalizar()
