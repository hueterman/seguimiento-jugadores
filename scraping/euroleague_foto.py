"""
Foto de los jugadores de Euroliga/EuroCup, desde la ficha de plantilla de su
club en euroleaguebasketball.net (NO desde la API api-live.euroleague.net:
confirmado el 2026-10-03 que su campo 'person.images' viene siempre como
objeto vacío {} - esa API no da fotos).

Confirmado el 2026-10-05:
- https://www.euroleaguebasketball.net/en/<euroleague|eurocup>/teams/<lo-
  que-sea>/roster/<codigo_club>/ es tolerante al slug igual que acb.com: el
  texto antes de "/roster/" no importa, solo el código de club final (el
  mismo 'code' que ya usamos en euroleague_api.obtener_clubes, en
  minúsculas). Esa página trae TODA la plantilla (jugadores y cuerpo
  técnico) en un único GET normal - una sola petición por club, igual de
  barata que la llamada a /people que ya hacíamos.
- OJO - primer intento fallido: en el navegador (que ejecuta JavaScript) la
  foto de cada jugador aparece como un <img class="...playerImage" alt=
  "NOMBRE APELLIDOS" data-srcset="...">, pero eso es ya el DOM procesado.
  En el HTML crudo que descarga 'requests' (sin ejecutar JavaScript, que es
  lo que de verdad usamos) NO hay ningún <img> de jugador - los datos
  vienen incrustados como JSON dentro del payload de streaming de Next.js
  (dentro de un <script>), y es el JavaScript del navegador el que
  construye esos <img> a partir de ese JSON ya en el cliente. Confirmado
  con un jugador real (Rasheed Bello, Virtus Bologna) pidiendo la página
  con 'requests' normal y mirando el HTML tal cual:
      {"firstName":"RASHEED","lastName":"BELLO",
       "cutoutImage":"https://media-cdn.cortextech.io/.../0cd10838....png",
       "tshirtNumber":"0","code":"014802","isAwayTeam":false,
       "url":"/euroleague/players/rasheed-bello/014802/"}
  Por eso ahora se extrae con una regex sobre ese JSON (ver _PATRON_JUGADOR),
  NO con BeautifulSoup buscando <img> - ese primer enfoque no funcionaba
  con un GET normal aunque sí "se veía" bien en el navegador. Mismo campo
  'code' que el id numérico final de la URL de la ficha del jugador (por si
  algún día hace falta sin pasar por el roster).
- Si un jugador no tiene foto, de momento no hay un caso real confirmado de
  cómo viene 'cutoutImage' en ese caso (null, "" u omitido) - el patrón
  admite los tres sin reventar, simplemente no se añade al diccionario.
- OJO: en apellidos compuestos con guión, el nombre puede venir con
  espacios alrededor ("ELIJAH MITROU - LONG") en vez de pegado como en
  nuestra BD ("Mitrou-Long") - normalizar_nombre() lo corrige para que el
  cruce por nombre funcione igual en ambos lados.

Uso de prueba:
    python -m scraping.euroleague_foto E VIR
    python -m scraping.euroleague_foto U ARI
"""
import argparse
import re

from scraping.base_scraper import crear_sesion, obtener_html

_LIGA_SLUG = {"E": "euroleague", "U": "eurocup"}

_Q = r'\\?"'  # la comilla puede venir escapada ('\"') o suelta ('"') según
# en qué nivel de anidado JSON caiga - ver docstring del módulo.
_PATRON_JUGADOR = re.compile(
    rf'{_Q}firstName{_Q}:{_Q}(?P<nombre>[^"\\]*){_Q},{_Q}lastName{_Q}:{_Q}(?P<apellidos>[^"\\]*){_Q}'
    rf'(?:(?!\}}).)*?{_Q}cutoutImage{_Q}:(?:null|{_Q}(?P<foto>[^"\\]*){_Q})',
)


def _url_roster(codigo_competicion: str, codigo_club: str) -> str:
    liga_slug = _LIGA_SLUG[codigo_competicion]
    return f"https://www.euroleaguebasketball.net/en/{liga_slug}/teams/x/roster/{codigo_club.lower()}/"


def normalizar_nombre(texto: str) -> str:
    """Clave de cruce: mayúsculas, sin espacios de más, y sin espacios
    alrededor de guiones ('ELIJAH MITROU - LONG' -> 'ELIJAH MITROU-LONG'),
    para que el nombre/apellidos de nuestra BD y el de la web caigan en la
    misma clave aunque difieran en ese detalle."""
    sin_guion = re.sub(r"\s*-\s*", "-", texto.strip())
    return re.sub(r"\s+", " ", sin_guion).upper()


def parsear_fotos_roster(html: str) -> dict[str, str]:
    """{'NOMBRE APELLIDOS' (normalizado): url_foto} para toda la gente con
    foto en el JSON incrustado de esa página de plantilla (jugadores y
    cuerpo técnico mezclados, si el cuerpo técnico usara la misma forma -
    quien use esto filtra por el nombre que le interese)."""
    fotos = {}
    for match in _PATRON_JUGADOR.finditer(html):
        foto_url = match.group("foto")
        if not foto_url:
            continue
        clave = normalizar_nombre(f"{match.group('nombre')} {match.group('apellidos')}")
        fotos[clave] = foto_url
    return fotos


def obtener_fotos_club(codigo_competicion: str, codigo_club: str) -> dict[str, str]:
    """Descarga y parsea la plantilla de un club (ver parsear_fotos_roster).
    Devuelve {} si la página no se puede descargar, sin lanzar excepción -
    un fallo al traer fotos no debe romper el resto de la actualización del
    club (estadísticas/trayectoria vía la API siguen funcionando igual)."""
    sesion = crear_sesion()
    html = obtener_html(sesion, _url_roster(codigo_competicion, codigo_club))
    if html is None:
        return {}
    return parsear_fotos_roster(html)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Muestra las fotos encontradas en la plantilla de un club de Euroliga/EuroCup."
    )
    parser.add_argument("codigo_competicion", choices=["E", "U"])
    parser.add_argument("codigo_club")
    args = parser.parse_args()
    for nombre, url in obtener_fotos_club(args.codigo_competicion, args.codigo_club).items():
        print(f"{nombre}: {url}")
