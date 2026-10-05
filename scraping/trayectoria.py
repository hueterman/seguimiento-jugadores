"""
Scraper de trayectoria (equipos por los que ha pasado un jugador), a partir
de la página "Trayectoria" de acb.com:
    https://acb.com/es/liga/jugadores/<slug>/trayectoria?editionId=<id>

A diferencia de la página de temporadas, esta NO expone los datos en una
tabla real, sino como texto repetido: "AAAA - AAAA" seguido del nombre del
equipo (confirmado sobre Luka Bozic: "2025 - 2026" / "Coviran Granada",
"2024 - 2025" / "Hiopos Lleida"...). El patrón se busca por texto en lugar
de por selector CSS, más robusto a cambios de clases. Probado contra un
fixture con esa misma estructura.

Un solo request devuelve el historial completo del jugador.
"""
import re
from typing import Optional

from bs4 import BeautifulSoup

from db.conexion import get_connection, obtener_o_crear_equipo
from scraping.base_scraper import crear_sesion, obtener_html

PATRON_TEMPORADA = re.compile(r"^(\d{4})\s*-\s*(\d{4})$")


def _url_trayectoria(slug_jugador: str, edition_id: int = 90) -> str:
    return f"https://acb.com/es/liga/jugadores/{slug_jugador}/trayectoria?editionId={edition_id}"


def _siguiente_texto_no_vacio(nodo) -> Optional[str]:
    """Recorre los siguientes nodos de texto del árbol hasta encontrar uno no vacío."""
    for siguiente in nodo.find_all_next(string=True):
        texto = siguiente.strip()
        if texto:
            return texto
    return None


def parsear_trayectoria(html: str) -> list[dict]:
    """
    Devuelve una lista de diccionarios {temporada, equipo}, uno por etapa,
    en el orden en que aparecen en la página (más reciente primero).
    """
    soup = BeautifulSoup(html, "html.parser")
    nodos_temporada = [
        nodo for nodo in soup.find_all(string=True)
        if PATRON_TEMPORADA.match(nodo.strip())
    ]

    etapas = []
    for nodo in nodos_temporada:
        temporada = nodo.strip().replace(" ", "")
        equipo = _siguiente_texto_no_vacio(nodo)
        if equipo:
            etapas.append({"temporada": temporada, "equipo": equipo})
    return etapas


def scrapear_trayectoria(slug_jugador: str, edition_id: int = 90) -> list[dict]:
    """Descarga y parsea la página de trayectoria de un jugador."""
    sesion = crear_sesion()
    html = obtener_html(sesion, _url_trayectoria(slug_jugador, edition_id))
    if html is None:
        return []
    return parsear_trayectoria(html)


def guardar_trayectoria(jugador_id: int, etapa: dict, competicion: str = "ACB",
                         **kwargs) -> None:
    """
    Inserta o actualiza una fila en trayectoria a partir de un registro
    devuelto por parsear_trayectoria()/scrapear_trayectoria() (o, para
    Euroliga/EuroCup, por scraping/euroleague_api.py). Crea el equipo si no
    existe. Idempotente: volver a ejecutarlo para el mismo jugador/equipo/
    temporada actualiza la fila existente en vez de duplicarla (requiere el
    índice único de trayectoria(jugador_id, equipo_id, temporada) - ver
    database/schema.sql). kwargs admite también 'pais', que se pasa al
    crear/completar el equipo (ver db.conexion.obtener_o_crear_equipo).
    """
    equipo_id = obtener_o_crear_equipo(
        etapa["equipo"], competicion=competicion, pais=kwargs.get("pais"),
    )
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO trayectoria
                (jugador_id, equipo_id, equipo_procedencia_id, temporada,
                 tipo_movimiento_id, fecha_inicio, fecha_fin, dorsal, rol)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(jugador_id, equipo_id, temporada)
            DO UPDATE SET
                equipo_procedencia_id = excluded.equipo_procedencia_id,
                tipo_movimiento_id = excluded.tipo_movimiento_id,
                fecha_inicio = excluded.fecha_inicio,
                fecha_fin = excluded.fecha_fin,
                dorsal = excluded.dorsal,
                rol = excluded.rol;
            """,
            (
                jugador_id, equipo_id, kwargs.get("equipo_procedencia_id"),
                etapa["temporada"], kwargs.get("tipo_movimiento_id"),
                kwargs.get("fecha_inicio"), kwargs.get("fecha_fin"),
                kwargs.get("dorsal"), kwargs.get("rol"),
            ),
        )
