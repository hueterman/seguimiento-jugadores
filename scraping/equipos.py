"""
Catálogo de los 18 equipos de ACB (temporada 2026-2027) y scraper de la
plantilla de un equipo (jugadores) a partir de acb.com.

Confirmado el 2026-10-03:
- La URL https://acb.com/es/liga/equipos/equipo-<id>/plantilla funciona con
  CUALQUIER texto antes del id - solo importa el número final (probado
  pidiendo "equipo-657" en vez del slug real "leyma-coruna-657" y devolvió
  la misma página). Por eso el catálogo de abajo solo necesita el id.
- Es una app Next.js. La plantilla real de jugadores SÍ viene en el HTML
  que devuelve un GET normal, dentro de una tarjeta con clase CSS que
  contiene "ResumenPlantillaCard" - pero la misma página mete además
  jugadores de OTROS equipos (un widget de líderes de los últimos
  partidos), así que hay que acotar la búsqueda a esa tarjeta en vez de
  coger todos los enlaces /liga/jugadores/ de la página entera
  (scraping/diagnosticar_plantilla.py lo confirma paso a paso).
- El cuerpo técnico (entrenadores) NO viene en ese HTML: ni el nombre del
  entrenador ni la palabra "Entrenador" aparecen en el HTML crudo (solo
  aparece como metadata interna de rutas de Next.js, no como contenido) -
  debe cargarse por JavaScript después de la carga inicial, algo que
  `requests` no ejecuta. Por eso los entrenadores se gestionan con alta
  manual (ver scraping/alta_entrenadores.py) en vez de scraping automático.
"""
import re

from bs4 import BeautifulSoup

from scraping.base_scraper import crear_sesion, obtener_html

# IDs confirmados el 2026-10-03 en la página de equipos de acb.com.
EQUIPOS_ACB: dict[int, str] = {
    8: "Joventut",
    2: "Barça",
    16: "Casademont Zaragoza",
    591: "Girona",
    658: "Lleida",
    10: "Manresa",
    3: "Baskonia",
    28: "La Laguna Tenerife",
    657: "Leyma Coruña",
    57: "Monbus Obradoiro",
    22: "MoraBanc Andorra",
    9: "Real Madrid",
    549: "San Pablo Burgos",
    25: "Río Breogán",
    4: "Surne Bilbao",
    12: "UCAM Murcia",
    14: "Unicaja",
    13: "Valencia Basket",
}

_PATRON_ENLACE_JUGADOR = re.compile(r"/es/liga/jugadores/([a-z0-9-]+)")
_PATRON_ID_FINAL = re.compile(r"-(\d+)$")

# El texto del enlace de cada jugador viene SIN separador entre el nombre
# abreviado y la posición (ej. "D. CuevasBase", "D. RadoncicAla-pívot") -
# confirmado el 2026-10-03. Se separan comprobando si termina en una de
# las posiciones del catálogo (ver database/schema.sql, tabla
# "posiciones") - "Ala-pívot" se comprueba ANTES que "Pívot" para no
# cortar mal ("Ala-pívot" también termina en "pívot").
_POSICIONES_CONOCIDAS = ["Ala-pívot", "Escolta", "Alero", "Pívot", "Base"]


def _separar_nombre_posicion(texto: str) -> tuple[str, str | None]:
    for posicion in _POSICIONES_CONOCIDAS:
        if texto.endswith(posicion):
            return texto[: -len(posicion)].strip(), posicion
    return texto, None


def _url_plantilla(team_id: int) -> str:
    return f"https://acb.com/es/liga/equipos/equipo-{team_id}/plantilla"


def _slug_a_nombre_apellidos(slug: str) -> tuple[str, str]:
    """'didac-cuevas-20212266' -> ('Didac', 'Cuevas').
    'alonzo-verge-jr-30003935' -> ('Alonzo', 'Verge-jr') - mismo criterio
    que se usó al dar de alta jugadores a mano (ver README de este
    directorio): el primer trozo es el nombre, el resto (unido con guion)
    son los apellidos, con may/min aproximadas (revisar a mano casos raros
    como sufijos "II"/"IV" si hiciera falta)."""
    sin_id = _PATRON_ID_FINAL.sub("", slug)
    partes = [p for p in sin_id.split("-") if p]
    if not partes:
        return slug, ""
    nombre = partes[0].capitalize()
    apellidos = "-".join(p.capitalize() for p in partes[1:])
    return nombre, apellidos


def parsear_plantilla(html: str) -> list[dict]:
    """Devuelve [{'nombre', 'apellidos', 'slug', 'posicion'}] SOLO de los
    jugadores del equipo (no del widget de líderes de otros partidos que
    mete la misma página) - ver docstring del módulo. 'posicion' es el
    nombre tal cual está en el catálogo (ver _POSICIONES_CONOCIDAS) o
    None si no se pudo reconocer."""
    soup = BeautifulSoup(html, "html.parser")
    tarjetas = soup.find_all(class_=re.compile("ResumenPlantillaCard"))
    # Tarjetas "hoja": sin otra tarjeta de la misma clase anidada dentro.
    # La plantilla real es la primera tarjeta hoja que SÍ contiene enlaces
    # a jugadores (las anteriores son contenedores vacíos de cabecera/nav).
    candidatas = [t for t in tarjetas if not t.find(class_=re.compile("ResumenPlantillaCard"))]

    enlaces_jugador = []
    for tarjeta in candidatas:
        enlaces = tarjeta.find_all("a", href=_PATRON_ENLACE_JUGADOR)
        if enlaces:
            enlaces_jugador = enlaces
            break

    jugadores = []
    vistos = set()
    for enlace in enlaces_jugador:
        match = _PATRON_ENLACE_JUGADOR.search(enlace.get("href", ""))
        if not match:
            continue
        slug = match.group(1)
        if slug in vistos:
            continue
        vistos.add(slug)
        nombre, apellidos = _slug_a_nombre_apellidos(slug)
        _, posicion = _separar_nombre_posicion(enlace.get_text(strip=True))
        jugadores.append({
            "nombre": nombre, "apellidos": apellidos, "slug": slug, "posicion": posicion,
        })
    return jugadores


def scrapear_plantilla(team_id: int) -> list[dict]:
    """Descarga y parsea la plantilla de un equipo (ver parsear_plantilla)."""
    sesion = crear_sesion()
    html = obtener_html(sesion, _url_plantilla(team_id))
    if html is None:
        return []
    return parsear_plantilla(html)
