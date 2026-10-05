"""
Alta masiva de jugadores: los crea en la BD (si no existen ya, buscando
por nombre y apellidos exactos) y trae sus estadísticas, trayectoria y
totales de carrera desde acb.com - todo en un solo comando, en vez de
repetir el formulario y el scraper jugador por jugador.

Uso:
    python -m scraping.alta_masiva <ruta_csv> [--edition-id 90]

El CSV necesita las columnas: nombre,apellidos,slug_acb
(ver scraping/jugadores_ejemplo.csv)
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from db.conexion import buscar_o_crear_jugador
from scraping.actualizar_jugador import actualizar_jugador


def alta_masiva(ruta_csv: str, edition_id: int = 90) -> None:
    with open(ruta_csv, newline="", encoding="utf-8") as f:
        filas = list(csv.DictReader(f))

    print(f"{len(filas)} jugadores en el CSV.\n")
    for fila in filas:
        nombre = fila["nombre"].strip()
        apellidos = fila["apellidos"].strip()
        slug = fila["slug_acb"].strip()

        jugador_id, creado = buscar_o_crear_jugador(nombre, apellidos)
        estado = "creado" if creado else "ya existía"
        print(f"=== {nombre} {apellidos} (id={jugador_id}, {estado}) ===")

        try:
            actualizar_jugador(jugador_id, slug, edition_id=edition_id)
        except Exception as error:
            print(f"  [ERROR] no se pudo actualizar {nombre} {apellidos}: {error}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Alta masiva de jugadores desde un CSV.")
    parser.add_argument("ruta_csv")
    parser.add_argument("--edition-id", type=int, default=90)
    args = parser.parse_args()
    alta_masiva(args.ruta_csv, edition_id=args.edition_id)
