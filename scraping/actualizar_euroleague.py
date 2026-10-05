"""
Alta/actualización automática de jugadores y cuerpo técnico desde la API de
Euroliga o EuroCup (ver scraping/euroleague_api.py para los detalles
confirmados de esa API).

A diferencia de acb.com, UNA sola llamada por club ya trae jugadores y
entrenadores juntos, así que no hace falta un paso separado de alta manual
para el cuerpo técnico como en ACB.

Dedup con jugadores de ACB: se busca/crea el jugador por nombre+apellidos
(db.conexion.buscar_o_crear_jugador), igual que en el flujo de ACB - un
jugador que juega ACB y Euroliga la misma temporada queda en UNA sola fila
de "jugadores". El "equipo" en cambio sí es una fila distinta por
competición (p.ej. "Real Madrid"/ACB y "Real Madrid"/Euroliga son dos filas
de "equipos" - ver db.conexion.obtener_o_crear_equipo), así que las
estadísticas/trayectoria de cada competición no se mezclan.

OJO - no se toca la posición del jugador (ver docstring de
scraping/euroleague_api.py: la posición de Euroliga no tiene la misma
granularidad que la española de ACB) ni su estado general (activo/lesionado/
etc. - eso es un dato de ACB o manual, no de esta fuente).

Uso:
    python -m scraping.actualizar_euroleague <euroliga|eurocup> <año> [--club <código>]

Ejemplos:
    python -m scraping.actualizar_euroleague euroliga 2026
    python -m scraping.actualizar_euroleague eurocup 2026 --club VAL
"""
import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from db.conexion import actualizar_datos_personales_jugador, buscar_o_crear_jugador, obtener_o_crear_equipo
from scraping.alta_entrenadores import guardar_entrenador
from scraping.euroleague_api import (
    CODIGOS_COMPETICION, NOMBRES_COMPETICION, codigo_temporada, obtener_clubes,
    obtener_roster_club, temporada_texto,
)
from scraping.euroleague_foto import normalizar_nombre, obtener_fotos_club
from scraping.trayectoria import guardar_trayectoria


def actualizar_club(nombre_competicion: str, codigo_competicion: str, codigo_temporada_: str,
                     codigo_club: str, info_club: dict, temporada: str) -> None:
    equipo_id = obtener_o_crear_equipo(
        info_club["nombre"], competicion=nombre_competicion, pais=info_club["pais"],
    )
    roster = obtener_roster_club(codigo_competicion, codigo_temporada_, codigo_club)
    print(f"  {len(roster)} personas (jugadores + cuerpo técnico) encontradas.")

    try:
        fotos = obtener_fotos_club(codigo_competicion, codigo_club)
    except Exception as error:
        print(f"  [AVISO] no se pudieron obtener fotos de la plantilla: {error}")
        fotos = {}

    for persona in roster:
        if persona["tipo"] == "jugador":
            jugador_id, creado = buscar_o_crear_jugador(persona["nombre"], persona["apellidos"])
            estado = "creado" if creado else "ya existía"
            clave_nombre = normalizar_nombre(f"{persona['nombre']} {persona['apellidos']}")
            actualizar_datos_personales_jugador(
                jugador_id,
                altura_cm=persona["altura_cm"],
                peso_kg=persona["peso_kg"],
                fecha_nacimiento=persona["fecha_nacimiento"],
                nacionalidad=persona["nacionalidad"],
                id_externo_euroleague=persona["id_externo"],
                foto_url=fotos.get(clave_nombre),
            )
            guardar_trayectoria(
                jugador_id,
                {"temporada": temporada, "equipo": info_club["nombre"]},
                competicion=nombre_competicion,
                pais=info_club["pais"],
                dorsal=persona["dorsal"],
                fecha_inicio=persona["fecha_inicio"],
                fecha_fin=persona["fecha_fin"],
            )
            print(f"    jugador: {persona['nombre']} {persona['apellidos']} (id={jugador_id}, {estado})")
        else:  # entrenador / entrenador ayudante
            guardar_entrenador(
                persona["nombre"], persona["apellidos"], persona["cargo"], equipo_id,
                temporada, id_externo_acb=persona["id_externo"], fuente_nombre="Scraping",
            )
            print(f"    {persona['cargo'].lower()}: {persona['nombre']} {persona['apellidos']}")


def actualizar_competicion(clave_competicion: str, anio: int, codigo_club: str | None = None) -> None:
    codigo_competicion = CODIGOS_COMPETICION[clave_competicion]
    nombre_competicion = NOMBRES_COMPETICION[clave_competicion]
    codigo_temporada_ = codigo_temporada(codigo_competicion, anio)
    temporada = temporada_texto(anio)

    clubes = obtener_clubes(codigo_competicion, codigo_temporada_)
    if codigo_club:
        if codigo_club not in clubes:
            print(f"No se encontró el club '{codigo_club}' en {nombre_competicion} {temporada}. "
                  f"Códigos disponibles: {', '.join(sorted(clubes))}")
            return
        clubes = {codigo_club: clubes[codigo_club]}

    print(f"{nombre_competicion} {temporada}: {len(clubes)} club(es) a actualizar.\n")
    for codigo, info_club in clubes.items():
        print(f"=== {info_club['nombre']} ({info_club['pais']}) [{codigo}] ===")
        try:
            actualizar_club(nombre_competicion, codigo_competicion, codigo_temporada_, codigo, info_club, temporada)
        except Exception as error:
            print(f"  [ERROR] no se pudo actualizar {info_club['nombre']}: {error}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Actualiza jugadores/entrenadores desde Euroliga o EuroCup.")
    parser.add_argument("competicion", choices=["euroliga", "eurocup"])
    parser.add_argument("anio", type=int, help="Año de inicio de temporada, ej. 2026 para 2026-2027.")
    parser.add_argument("--club", help="Código de un solo club (ej. MAD, BAR). Si se omite, toda la competición.")
    args = parser.parse_args()
    actualizar_competicion(args.competicion, args.anio, codigo_club=args.club)
