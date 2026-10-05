"""
Diagnóstico puntual (v4): las cabeceras de navegador real NO cambiaron
nada (seguía sin aparecer el cuerpo técnico), así que el problema no era
el User-Agent. Esta versión prueba otra hipótesis: visitar primero la
página "Resumen" del equipo con la misma sesión (para que se guarden las
cookies que ponga el sitio) y LUEGO pedir la página de plantilla con esa
misma sesión "calentada", en vez de pedir la plantilla en frío como hasta
ahora.

Uso:
    python -m scraping.diagnosticar_plantilla <team_id> [nombre_a_buscar ...]
"""
import argparse
import re

from bs4 import BeautifulSoup

from scraping.base_scraper import crear_sesion, obtener_html

_PATRON_ENLACE = re.compile(r"/es/liga/(jugadores|entrenadores)/([a-z0-9-]+)")


def _url_resumen(team_id: int) -> str:
    return f"https://acb.com/es/liga/equipos/equipo-{team_id}"


def _url_plantilla(team_id: int) -> str:
    return f"https://acb.com/es/liga/equipos/equipo-{team_id}/plantilla"


def _buscar_nombres(html: str, nombres: list[str], etiqueta: str) -> None:
    print(f"=== Búsqueda de nombres en el HTML ({etiqueta}) ===")
    for nombre in nombres:
        apariciones = [m.start() for m in re.finditer(re.escape(nombre), html, re.IGNORECASE)]
        print(f"'{nombre}': {len(apariciones)} aparición/es")
        for inicio in apariciones[:2]:
            desde, hasta = max(0, inicio - 150), min(len(html), inicio + 150)
            print(f"    ...{html[desde:hasta]}...")
    print()


def diagnosticar(team_id: int, nombres_buscar: list[str]) -> None:
    sesion = crear_sesion()

    url_resumen = _url_resumen(team_id)
    print(f"1) Visitando primero (para coger cookies): {url_resumen}")
    html_resumen = obtener_html(sesion, url_resumen)
    if html_resumen is None:
        print("   No se pudo descargar.")
    else:
        print(f"   OK, {len(html_resumen)} caracteres. Cookies tras esta visita:")
        print(f"   {dict(sesion.cookies)}")
    print()

    url_plantilla = _url_plantilla(team_id)
    print(f"2) Pidiendo la plantilla CON la misma sesión: {url_plantilla}")
    html_plantilla = obtener_html(sesion, url_plantilla)
    if html_plantilla is None:
        print("   No se pudo descargar.")
        return
    print(f"   OK, {len(html_plantilla)} caracteres.\n")

    _buscar_nombres(html_plantilla, nombres_buscar, "sesión calentada con la visita al Resumen")

    soup = BeautifulSoup(html_plantilla, "html.parser")
    enlaces_entrenador = soup.find_all("a", href=re.compile(r"/es/liga/entrenadores/"))
    print(f"Enlaces a /liga/entrenadores/ encontrados: {len(enlaces_entrenador)}")
    for enlace in enlaces_entrenador[:5]:
        print(f"    {enlace.get('href')!r} -> {enlace.get_text(strip=True)!r}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("team_id", type=int)
    parser.add_argument("nombres", nargs="*", help="Nombres conocidos a buscar en el HTML crudo")
    args = parser.parse_args()
    diagnosticar(args.team_id, args.nombres)
