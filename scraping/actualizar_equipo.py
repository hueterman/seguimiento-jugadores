"""
Actualiza automáticamente todos los jugadores de un equipo (o de toda la
liga ACB) a partir de su plantilla en acb.com: crea en la BD los jugadores
que no existan todavía (buscando por nombre+apellidos exactos, igual que
scraping/alta_masiva.py) y trae sus estadísticas/trayectoria - sin tener
que escribirlos a mano uno por uno.

Uso:
    python -m scraping.actualizar_equipo <team_id> [--edition-id 90]
    python -m scraping.actualizar_equipo --liga [--edition-id 90]

Ejemplos:
    python -m scraping.actualizar_equipo 657      # solo Leyma Coruña
    python -m scraping.actualizar_equipo --liga   # los 18 equipos de ACB

IDs de equipo: ver scraping/equipos.py (EQUIPOS_ACB).
"""
import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from db.conexion import buscar_o_crear_jugador, actualizar_posicion_jugador
from scraping.actualizar_jugador import actualizar_jugador
from scraping.equipos import EQUIPOS_ACB, scrapear_plantilla


def actualizar_equipo(team_id: int, edition_id: int = 90) -> None:
    nombre_equipo = EQUIPOS_ACB.get(team_id, f"equipo {team_id}")
    print(f"=== {nombre_equipo} (id acb.com {team_id}) ===")

    jugadores = scrapear_plantilla(team_id)
    print(f"{len(jugadores)} jugadores en la plantilla.\n")

    for jugador in jugadores:
        jugador_id, creado = buscar_o_crear_jugador(jugador["nombre"], jugador["apellidos"])
        estado = "creado" if creado else "ya existía"
        print(f"--- {jugador['nombre']} {jugador['apellidos']} (id={jugador_id}, {estado}) ---")
        actualizar_posicion_jugador(jugador_id, jugador.get("posicion"))
        try:
            actualizar_jugador(jugador_id, jugador["slug"], edition_id=edition_id)
        except Exception as error:
            print(f"  [ERROR] no se pudo actualizar: {error}")
        print()


def actualizar_liga(edition_id: int = 90) -> None:
    print(f"{len(EQUIPOS_ACB)} equipos en ACB.\n")
    for team_id in EQUIPOS_ACB:
        actualizar_equipo(team_id, edition_id=edition_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Actualiza jugadores de un equipo de ACB, o de toda la liga, desde acb.com."
    )
    parser.add_argument("team_id", type=int, nargs="?", help="ID de acb.com del equipo (omite si usas --liga)")
    parser.add_argument("--liga", action="store_true", help="Actualiza los 18 equipos de ACB")
    parser.add_argument("--edition-id", type=int, default=90)
    args = parser.parse_args()

    if args.liga:
        actualizar_liga(edition_id=args.edition_id)
    elif args.team_id is not None:
        actualizar_equipo(args.team_id, edition_id=args.edition_id)
    else:
        parser.error("Indica un team_id (ver scraping/equipos.py) o usa --liga.")
