"""
Backfill de estadisticas_temporada y estadisticas_carrera (Euroliga y
EuroCup) para TODOS los jugadores que ya tienen id_externo_euroleague en
la BD (venga de la fusión ACB+Euroliga o de un jugador solo de
Euroliga/EuroCup). Usa scraping/euroleague_estadisticas.py, que ya está
confirmado y probado contra datos reales (ver su docstring).

Para cada jugador se prueban las DOS competiciones (Euroliga y EuroCup),
porque no sabemos de antemano en cuál(es) ha jugado a lo largo de su
carrera - el 'person.code' (id_externo_euroleague) es el mismo en ambas,
lo que varía es si esa ficha existe en esa competición. Si una
competición no tiene ficha para ese jugador (404) o no se encuentra la
tabla de estadísticas, se descarta sin guardar nada ahí - no es un error,
simplemente esa competición no aplica a ese jugador.

IMPORTANTE: ejecutar esto en tu PROPIO PowerShell, NUNCA a través de
Claude:
- Hace peticiones HTTP a euroleaguebasketball.net, que no está en la
  lista de hosts permitidos por el proxy de Claude (confirmado el
  2026-10-03 - ver scraping/euroleague_estadisticas.py).
- Escribe en la base de datos en vivo, y ya se ha visto que escribir en
  ella a través del puente puede dar 'disk I/O error' (ver
  database/normalizar_nacionalidades.py).

Uso:
    python -m scraping.actualizar_estadisticas_euroleague
    python -m scraping.actualizar_estadisticas_euroleague --solo-id 123
    python -m scraping.actualizar_estadisticas_euroleague --solo-apellidos "Micic,Mirotic" --debug
"""
import argparse
import sys
import time
import traceback
from pathlib import Path
from typing import Optional

sys.path.append(str(Path(__file__).resolve().parent.parent))
from db.conexion import get_connection
from scraping.euroleague_estadisticas import actualizar_estadisticas_jugador

PAUSA_ENTRE_PETICIONES = 1.0  # segundos, por cortesía con el servidor


def jugadores_euroleague() -> list[dict]:
    with get_connection() as conn:
        filas = conn.execute(
            "SELECT id, nombre, apellidos, id_externo_euroleague FROM jugadores "
            "WHERE id_externo_euroleague IS NOT NULL "
            "ORDER BY apellidos COLLATE NOCASE;"
        ).fetchall()
    return [dict(f) for f in filas]


def actualizar_todos(solo_id: Optional[int] = None, solo_apellidos: Optional[list[str]] = None,
                      debug: bool = False) -> None:
    jugadores = jugadores_euroleague()
    if solo_id is not None:
        jugadores = [j for j in jugadores if j["id"] == solo_id]
        if not jugadores:
            print(f"No hay ningún jugador con id={solo_id} e id_externo_euroleague no nulo.")
            return
    if solo_apellidos:
        objetivo = [a.strip().lower() for a in solo_apellidos]
        jugadores = [j for j in jugadores if any(a in j["apellidos"].lower() for a in objetivo)]
        if not jugadores:
            print(f"No hay ningún jugador cuyo apellido contenga: {', '.join(solo_apellidos)}")
            return

    print(f"{len(jugadores)} jugador(es) con id_externo_euroleague.\n")

    # Compartida entre TODOS los jugadores de este proceso: una temporada
    # (p.ej. "E2022") solo se pide una vez a la API aunque la jueguen
    # cientos de jugadores distintos - antes se repetía por cada jugador,
    # lo que eran miles de peticiones de más y probablemente la causa de
    # los errores intermitentes vistos en el primer backfill masivo.
    cache_clubes_global: dict = {}

    total_temporadas = 0
    jugadores_con_datos = 0
    jugadores_con_error = []
    for i, j in enumerate(jugadores, 1):
        nombre_completo = f"{j['nombre']} {j['apellidos']}"
        print(f"[{i}/{len(jugadores)}] {nombre_completo} (código {j['id_externo_euroleague']})")
        guardadas_este_jugador = 0
        for codigo_competicion in ("E", "U"):
            try:
                n = actualizar_estadisticas_jugador(
                    j["id"], j["nombre"], j["apellidos"], j["id_externo_euroleague"], codigo_competicion,
                    cache_clubes=cache_clubes_global,
                )
            except Exception as error:
                if debug:
                    traceback.print_exc()
                else:
                    print(f"    [error] {codigo_competicion}: {error}")
                jugadores_con_error.append(nombre_completo)
                n = 0
            if n:
                etiqueta = "Euroliga" if codigo_competicion == "E" else "EuroCup"
                print(f"    {etiqueta}: {n} temporada(s) guardada(s).")
                total_temporadas += n
                guardadas_este_jugador += n
            time.sleep(PAUSA_ENTRE_PETICIONES)
        if guardadas_este_jugador:
            jugadores_con_datos += 1
        else:
            print("    (sin ficha de estadísticas en ninguna de las dos competiciones)")

    print(
        f"\nListo. {jugadores_con_datos}/{len(jugadores)} jugador(es) con estadísticas guardadas "
        f"({total_temporadas} fila(s) de temporada en total)."
    )
    if jugadores_con_error:
        print(f"Jugador(es) con algún error durante el proceso: {', '.join(jugadores_con_error)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill de estadísticas Euroliga/EuroCup para jugadores ya conocidos."
    )
    parser.add_argument("--solo-id", type=int, default=None, help="Actualizar solo el jugador con este id (para probar).")
    parser.add_argument("--solo-apellidos", type=str, default=None,
                         help="Lista separada por comas; solo jugadores cuyo apellido contenga alguno (para reproducir un error puntual).")
    parser.add_argument("--debug", action="store_true", help="Imprime el traceback completo en caso de error, en vez de solo el mensaje.")
    args = parser.parse_args()
    lista_apellidos = args.solo_apellidos.split(",") if args.solo_apellidos else None
    actualizar_todos(args.solo_id, lista_apellidos, args.debug)
