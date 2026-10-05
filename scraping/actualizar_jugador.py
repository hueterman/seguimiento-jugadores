"""
Actualiza estadísticas y trayectoria de un jugador ya existente en la BD,
a partir de su slug de acb.com (la parte de la URL tras /jugadores/, p.ej.
"luka-bozic-30003420" para https://acb.com/es/liga/jugadores/luka-bozic-30003420).

Uso:
    python -m scraping.actualizar_jugador <jugador_id> <slug_acb> [--edition-id 90]

Ejemplo:
    python -m scraping.actualizar_jugador 1 luka-bozic-30003420
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from db.conexion import get_connection, actualizar_datos_personales_jugador, actualizar_posicion_jugador
from scraping.estadisticas import (
    scrapear_pagina_temporadas, guardar_estadisticas, guardar_estadisticas_carrera,
)
from scraping.ficha_jugador import scrapear_ficha_jugador
from scraping.trayectoria import scrapear_trayectoria, guardar_trayectoria


def _id_externo_desde_slug(slug: str) -> str | None:
    """'luka-bozic-30003420' -> '30003420' (el número final del slug)."""
    match = re.search(r"-(\d+)$", slug)
    return match.group(1) if match else None


def actualizar_jugador(jugador_id: int, slug_acb: str, edition_id: int = 90) -> None:
    with get_connection() as conn:
        existe = conn.execute("SELECT 1 FROM jugadores WHERE id = ?;", (jugador_id,)).fetchone()
    if not existe:
        print(
            f"No existe ningún jugador con id={jugador_id} en la base de datos.\n"
            "Este script solo actualiza estadísticas/trayectoria de un jugador que ya existe:\n"
            "  1. Crea primero el jugador desde el formulario: http://127.0.0.1:5500/jugadores/nuevo\n"
            "  2. Mira qué id le ha tocado en http://127.0.0.1:5500/ (la lista de jugadores)\n"
            "  3. Vuelve a ejecutar este comando con ese id."
        )
        return

    id_externo = _id_externo_desde_slug(slug_acb)
    if id_externo:
        with get_connection() as conn:
            conn.execute(
                "UPDATE jugadores SET id_externo_acb = ?, fecha_actualizacion = datetime('now') WHERE id = ?;",
                (id_externo, jugador_id),
            )

    ficha = scrapear_ficha_jugador(slug_acb)
    actualizar_datos_personales_jugador(
        jugador_id,
        altura_cm=ficha["altura_cm"],
        fecha_nacimiento=ficha["fecha_nacimiento"],
        nacionalidad=ficha["nacionalidad"],
        foto_url=ficha["foto_url"],
    )
    actualizar_posicion_jugador(jugador_id, ficha["posicion"])
    datos_encontrados = ", ".join(
        f"{clave}={valor}" for clave, valor in ficha.items() if valor is not None
    ) or "ninguno"
    print(f"Datos personales encontrados en la ficha: {datos_encontrados}")

    temporadas, carrera = scrapear_pagina_temporadas(slug_acb, edition_id=edition_id)
    print(f"Temporadas encontradas: {len(temporadas)}")
    for registro in temporadas:
        guardar_estadisticas(jugador_id, registro)
        print(f"  guardada: {registro['temporada']} ({registro['club']})")

    print(f"Agregados de carrera encontrados: {len(carrera)}")
    for tipo_fila, registro in carrera.items():
        guardar_estadisticas_carrera(jugador_id, tipo_fila, registro)
        print(f"  guardado: {tipo_fila}")

    trayectoria = scrapear_trayectoria(slug_acb, edition_id=edition_id)
    print(f"Etapas de trayectoria encontradas: {len(trayectoria)}")
    for etapa in trayectoria:
        guardar_trayectoria(jugador_id, etapa)
        print(f"  guardada: {etapa['temporada']} ({etapa['equipo']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Actualiza un jugador desde acb.com.")
    parser.add_argument("jugador_id", type=int)
    parser.add_argument("slug_acb")
    parser.add_argument("--edition-id", type=int, default=90)
    args = parser.parse_args()
    actualizar_jugador(args.jugador_id, args.slug_acb, edition_id=args.edition_id)
