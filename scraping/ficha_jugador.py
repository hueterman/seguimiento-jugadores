"""
Scraper de la ficha personal de un jugador en acb.com (altura, fecha de
nacimiento, nacionalidad) - la página https://acb.com/es/liga/jugadores/<slug>.

Confirmado el 2026-10-03 (ver sesión del puente al navegador del usuario):
estos datos SÍ vienen en el HTML que devuelve un GET normal (no hace falta
JavaScript, a diferencia del cuerpo técnico de scraping/equipos.py), dentro
de un grid con clase CSS que contiene "playerInfoGrid": una lista de
tarjetas "playerInfoGrid__item", cada una con dos <p> (etiqueta y valor).
Ejemplo real (Alberto Abalde):
    Posición -> "Alero"
    Altura -> "2,02 m"
    Fecha nacimiento -> "15/12/1995 (30 años)"
    Lugar nacimiento -> "Ferrol, España"
    Nacionalidad -> "España"
    Licencia -> "JFL"
No hay ningún campo de peso en esta página (confirmado buscando "Peso" en
el HTML crudo: 0 apariciones) - por eso no se scrapea.

Foto del jugador (confirmada el 2026-10-04 inspeccionando el HTML crudo):
va en un <img> cuya clase contiene "playerImageNoBackground", servido a
través del optimizador de imágenes de Next.js
("/_next/image?url=<foto real>&w=...&q=..."); _extraer_foto() se queda con
el parámetro "url" (la foto real en static.acb.com, sin los parámetros de
tamaño/calidad de Next.js). SÍ está en el HTML que devuelve un GET normal
(no es un <img> que se rellene por JavaScript después de cargar la
página) - confirmado comparando el HTML crudo (requests/fetch sin
ejecutar JS) con el DOM ya renderizado. Si acb.com cambia la plantilla o
el jugador no tiene foto, se devuelve None sin romper el resto del scraping.

Uso:
    python -m scraping.ficha_jugador <slug_acb>

Ejemplo:
    python -m scraping.ficha_jugador alberto-abalde-20210088
"""
import argparse
import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from scraping.base_scraper import crear_sesion, obtener_html

_PATRON_ALTURA = re.compile(r"(\d+)[,.](\d+)\s*m")
_PATRON_FECHA = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def _url_ficha(slug_acb: str) -> str:
    return f"https://acb.com/es/liga/jugadores/{slug_acb}"


def _altura_a_cm(texto: str) -> int | None:
    """'2,02 m' -> 202."""
    match = _PATRON_ALTURA.search(texto)
    if not match:
        return None
    metros, centesimas = match.groups()
    return int(metros) * 100 + int(centesimas)


def _fecha_a_iso(texto: str) -> str | None:
    """'15/12/1995 (30 años)' -> '1995-12-15'."""
    match = _PATRON_FECHA.search(texto)
    if not match:
        return None
    dia, mes, anio = match.groups()
    return f"{anio}-{mes}-{dia}"


def _extraer_foto(soup: BeautifulSoup) -> str | None:
    """Foto del jugador - ver docstring del módulo. None si no hay <img> con
    esa clase, si no tiene 'src', o si el 'src' no tiene pinta de URL."""
    img = soup.find("img", class_=re.compile(r"playerImageNoBackground"))
    if img is None or not img.get("src"):
        return None
    src = img["src"]
    valores = parse_qs(urlparse(src).query).get("url")
    if valores:
        return valores[0]
    return src if src.startswith("http") else None


def parsear_ficha(html: str) -> dict:
    """Devuelve {'altura_cm', 'fecha_nacimiento', 'nacionalidad', 'posicion',
    'foto_url'} (valores a None si no se encuentran). Busca por el texto de
    la etiqueta en vez de por posición en la lista, para no depender de que
    todas las fichas tengan exactamente las mismas tarjetas en el mismo
    orden."""
    soup = BeautifulSoup(html, "html.parser")
    tarjetas = soup.find_all(class_=re.compile(r"playerInfoGrid__item"))

    etiquetas = {}
    for tarjeta in tarjetas:
        parrafos = tarjeta.find_all("p")
        if len(parrafos) < 2:
            continue
        etiqueta = parrafos[0].get_text(strip=True)
        valor = parrafos[1].get_text(strip=True)
        etiquetas[etiqueta] = valor

    return {
        "altura_cm": _altura_a_cm(etiquetas["Altura"]) if "Altura" in etiquetas else None,
        "fecha_nacimiento": _fecha_a_iso(etiquetas["Fecha nacimiento"]) if "Fecha nacimiento" in etiquetas else None,
        "nacionalidad": etiquetas.get("Nacionalidad"),
        "posicion": etiquetas.get("Posición"),
        "foto_url": _extraer_foto(soup),
    }


def scrapear_ficha_jugador(slug_acb: str) -> dict:
    """Descarga y parsea la ficha de un jugador (ver parsear_ficha). Si no
    se puede descargar la página, devuelve todos los valores a None."""
    sesion = crear_sesion()
    html = obtener_html(sesion, _url_ficha(slug_acb))
    if html is None:
        return {
            "altura_cm": None, "fecha_nacimiento": None, "nacionalidad": None,
            "posicion": None, "foto_url": None,
        }
    return parsear_ficha(html)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Muestra la ficha personal de un jugador en acb.com.")
    parser.add_argument("slug_acb")
    args = parser.parse_args()
    print(scrapear_ficha_jugador(args.slug_acb))
