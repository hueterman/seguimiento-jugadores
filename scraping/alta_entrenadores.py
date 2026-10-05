"""
Alta (manual) de entrenadores desde un CSV: no se puede scrapear como a
los jugadores porque acb.com carga el cuerpo técnico por JavaScript (ver
docstring de scraping/equipos.py) - así que esto se rellena a mano una vez
por equipo/temporada, algo razonable dado que son pocas personas y
cambian poco durante la temporada.

Uso:
    python -m scraping.alta_entrenadores <ruta_csv>

El CSV necesita las columnas: nombre,apellidos,cargo,equipo,temporada,slug_acb
(slug_acb es opcional, puede dejarse vacío)
"""
import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from db.conexion import get_connection, obtener_o_crear_equipo, id_por_nombre

_PATRON_ID_FINAL = re.compile(r"-(\d+)$")


def _id_externo_desde_slug(slug: str) -> str | None:
    if not slug:
        return None
    match = _PATRON_ID_FINAL.search(slug)
    return match.group(1) if match else None


def guardar_entrenador(nombre: str, apellidos: str, cargo: str, equipo_id: int,
                        temporada: str, id_externo_acb: str | None = None,
                        fuente_nombre: str = "Manual") -> None:
    """fuente_nombre debe existir en el catálogo 'fuentes' (ver
    database/schema.sql: 'Manual', 'Scraping', 'Prensa', 'Estimado').
    Por defecto 'Manual' (altas por CSV como hasta ahora); el alta
    automática de Euroliga/EuroCup (scraping/actualizar_euroleague.py) pasa
    'Scraping'."""
    fuente_id = id_por_nombre("fuentes", fuente_nombre)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO entrenadores
                (nombre, apellidos, cargo, equipo_id, temporada, id_externo_acb, fuente_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(nombre, apellidos, equipo_id, temporada)
            DO UPDATE SET
                cargo = excluded.cargo,
                id_externo_acb = excluded.id_externo_acb,
                fuente_id = excluded.fuente_id,
                fecha_actualizacion = datetime('now');
            """,
            (nombre, apellidos, cargo, equipo_id, temporada, id_externo_acb, fuente_id),
        )


def alta_entrenadores(ruta_csv: str) -> None:
    with open(ruta_csv, newline="", encoding="utf-8") as f:
        filas = list(csv.DictReader(f))

    print(f"{len(filas)} entrenadores en el CSV.\n")
    for fila in filas:
        nombre = fila["nombre"].strip()
        apellidos = fila["apellidos"].strip()
        cargo = fila["cargo"].strip()
        equipo = fila["equipo"].strip()
        temporada = fila["temporada"].strip()
        slug = (fila.get("slug_acb") or "").strip()

        equipo_id = obtener_o_crear_equipo(equipo, competicion="ACB")
        guardar_entrenador(
            nombre, apellidos, cargo, equipo_id, temporada,
            id_externo_acb=_id_externo_desde_slug(slug),
        )
        print(f"  guardado: {nombre} {apellidos} - {cargo} ({equipo}, {temporada})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Alta de entrenadores desde un CSV.")
    parser.add_argument("ruta_csv")
    args = parser.parse_args()
    alta_entrenadores(args.ruta_csv)
