"""
Scraper de estadísticas de Euroliga/EuroCup POR TEMPORADA y de CARRERA, a
partir de la ficha pública del jugador en euroleaguebasketball.net - NO es
la misma fuente que scraping/euroleague_api.py (esa es la API JSON
api-live.euroleague.net, que solo da roster/datos personales/trayectoria,
sin estadísticas de juego). Esta es una web aparte (Next.js), confirmada
el 2026-10-03 inspeccionando en vivo con el navegador la ficha de Sasha
Vezenkov:
    https://www.euroleaguebasketball.net/es/euroleague/players/vezenkov-sasha/003469/

Hallazgos confirmados sobre el DOM en vivo (pendiente de confirmar que el
HTML crudo, sin ejecutar JS, trae lo mismo - ver diagnosticar()):
- La tabla de temporada/carrera NO se carga por una llamada JS aparte (se
  comprobó la pestaña de red: cero llamadas a api-live ni a ningún otro
  endpoint JSON para esta tabla) - los números ya están en el DOM.
- Está maquetada como una rejilla de "colGroup" (columnas verticales), NO
  como una tabla HTML normal <table>. Cada colGroup tiene el MISMO número
  de filas, alineadas por índice - la fila i de cada colGroup pertenece a
  la misma fila lógica de la tabla.
- El colGroup de "Temporada" se identifica por contener la palabra
  "Temporada" en su fila de cabecera (fila índice 1; la fila índice 0 es
  un separador vacío). Cada fila de temporada real es un <button> con
  atributos `data-season-code` (p.ej. "E2018" - MISMO formato que ya usa
  scraping/euroleague_api.py: letra de competición + año de inicio) y
  `data-team-code` (p.ej. "OLY" - el código de 3 letras del club, se
  espera que sea el mismo código que usa la API de clubes). Las filas
  "Total" y "Media" (agregados de carrera) NO tienen esos atributos.
- A partir del colGroup de "Temporada", los siguientes colGroups (mismo
  número de filas) completan esa misma fila lógica con el resto de
  columnas, hasta llegar al colGroup cuya cabecera es "PIR" (inclusive):
  G/GS, Min/Pts/2FG/3FG/FT, Rebotes O/D/T, As/St/To, Bloqueos Fv/Ag,
  Faltas Cm/Rv, PIR.
- A diferencia de acb.com (que solo publica PROMEDIOS por partido en la
  fila de cada temporada), aquí la fila de cada TEMPORADA ya trae
  TOTALES reales (minutos, puntos, tiros convertidos/intentados,
  rebotes, etc.) - solo la fila "Media" (carrera) da promedios. Esto es
  mejor calidad de dato que ACB: no hace falta estimar nada.

Resolución del equipo: en vez de intentar traducir el código de 3 letras
del club ("OLY") a un nombre completo con un catálogo propio, se reutiliza
scraping.euroleague_api.obtener_clubes(codigo_competicion, codigo_temporada)
(ya implementado y probado) para esa temporada exacta, y se busca el
código de club en el resultado - así se obtiene el nombre completo y el
país ya traducidos a español, con el mismo código ya usado para roster.

CONFIRMADO el 2026-10-03, ejecutado por el usuario en su propio PowerShell:
la descarga con requests + cabeceras de navegador normales funciona sin
problema (11 temporadas de Vezenkov parseadas correctamente, datos
idénticos a los mostrados en la web real). El 403 que había dado antes
WebFetch (herramienta en la nube de Anthropic) era del PROXY de Claude,
no del sitio - tanto desde la nube como desde el puente al ordenador del
usuario, ese dominio no está en la lista de hosts permitidos por ese
proxy. Por eso cualquier descarga real de este módulo debe ejecutarse
TAL CUAL en el PowerShell del propio usuario (igual que ya se hace con
database/normalizar_nacionalidades.py y con las pruebas reales de
scraping/euroleague_api.py) - nunca desde las herramientas de Claude.

También CONFIRMADO: EuroCup usa exactamente la misma estructura de tabla
(mismo prefijo de clases, mismos atributos data-season-code/data-team-code
con el código "U" en vez de "E") - este módulo vale para ambas
competiciones sin ningún cambio, solo pasando codigo_competicion="U".

Uso de prueba (ejecutar en tu propio PowerShell, no sirve desde la nube):
    python -m scraping.euroleague_estadisticas diagnosticar 003469 vezenkov-sasha E
"""
import argparse
import re
import unicodedata
from typing import Optional

import requests
from bs4 import BeautifulSoup

from db.conexion import actualizar_posicion_jugador, get_connection, obtener_o_crear_equipo
from scraping.estadisticas import guardar_estadisticas_carrera
from scraping.euroleague_api import CODIGOS_COMPETICION, NOMBRES_COMPETICION, obtener_clubes, temporada_texto

_NOMBRE_COMPETICION_POR_CODIGO = {v: NOMBRES_COMPETICION[k] for k, v in CODIGOS_COMPETICION.items()}

# Códigos de club usados en la ficha de estadísticas del jugador que NO
# coinciden con el código que da la API de clubes (api-live.euroleague.net)
# para esa misma temporada - visto sobre todo en temporadas antiguas,
# donde la API solo expone el código VIGENTE del club y la ficha conserva
# el código histórico. Confirmado el 2026-10-03: 'ALB' (ficha, temporada
# E2014) es ALBA Berlin, que en la API de esa temporada tiene código
# 'BER'. Ampliar este diccionario conforme se identifiquen más casos -
# los que no estén aquí se guardan con el propio código como nombre de
# equipo provisional (ver actualizar_estadisticas_jugador), sin perder
# los datos, a la espera de identificarlos.
_ALIAS_CODIGO_CLUB = {
    "ALB": "BER",
}

# Posición tal como aparece en la cabecera de la ficha (locale "es"),
# normalizada al valor EXACTO del catálogo 'posiciones' (ver
# database/schema.sql). Confirmado el 2026-10-04 navegando la ficha real
# de Nicola Akele: la versión en español de la web normalmente distingue
# las 5 posiciones de nuestro catálogo, solo que sin tilde. Pero para
# algunos jugadores (visto en el backfill real: Michael Caffey, Nick
# Calathes) la ficha solo da la categoría genérica "Guardia" (equivalente
# al "Guard" de 3 valores de la API JSON - ver scraping/euroleague_api.py).
# A petición del usuario, "Guardia" se asigna a "Escolta" en vez de
# descartarse (decisión explícita, no deducida: no hay forma de saber si
# un "Guardia" genérico es realmente Base o Escolta).
_POSICIONES_WEB = {
    "base": "Base",
    "escolta": "Escolta",
    "alero": "Alero",
    "ala-pivot": "Ala-pívot",
    "pivot": "Pívot",
    "guardia": "Escolta",
}

_CABECERAS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}

_PREFIJO_URL = "https://www.euroleaguebasketball.net"
_RUTA_COMPETICION = {"E": "euroleague", "U": "eurocup"}

# Una temporada de liga real es letra de competición + año de 4 cifras
# (p.ej. 'E2018'). Cualquier otra cosa ('TBO25', 'TF424', 'TM24'...) es un
# torneo/evento especial que la ficha mezcla en la misma tabla - ver uso
# en parsear_tabla_temporadas.
_PATRON_CODIGO_TEMPORADA = re.compile(r"^[A-Z]\d{4}$")


def _slug(nombre: str, apellidos: str) -> str:
    """CONFIRMADO el 2026-10-03 (navegando con un slug inventado,
    'cualquier-cosa-x', y comprobando que la ficha de Vezenkov cargó igual):
    el slug de texto en la URL es puramente decorativo - el servidor solo
    mira el código numérico final. No hace falta que coincida con el orden
    real nombre/apellidos que usa el sitio (se ha visto tanto
    'apellido-nombre' como 'nombre-apellido' según el jugador)."""
    texto = f"{nombre}-{apellidos}".strip().lower()
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", "-", sin_tildes).strip("-")


def url_ficha_jugador(codigo_competicion: str, nombre: str, apellidos: str, id_externo: str, idioma: str = "es") -> str:
    ruta = _RUTA_COMPETICION[codigo_competicion]
    return f"{_PREFIJO_URL}/{idioma}/{ruta}/players/{_slug(nombre, apellidos)}/{id_externo}/"


def _sesion() -> requests.Session:
    sesion = requests.Session()
    sesion.headers.update(_CABECERAS)
    return sesion


def obtener_html_ficha(url: str) -> Optional[str]:
    """Descarga el HTML de la ficha. None (con aviso) si falla - igual de
    tolerante que scraping/base_scraper.py para no tirar abajo un proceso
    por lotes por un jugador concreto."""
    try:
        respuesta = _sesion().get(url, timeout=15)
        respuesta.raise_for_status()
        return respuesta.text
    except requests.RequestException as error:
        print(f"  [aviso] no se pudo descargar {url}: {error}")
        return None


def extraer_posicion(html: str) -> Optional[str]:
    """Devuelve el valor exacto del catálogo 'posiciones' a partir de la
    cabecera de la ficha ("#45 · Ala-Pivot"), o None si no se encuentra o
    no se reconoce el texto.

    Se busca por ESTRUCTURA, no por nombre de clase CSS (clases Tailwind
    utilitarias, más frágil fiarse de su valor exacto que de la forma):
    confirmado el 2026-10-04 inspeccionando en vivo la ficha de Nicola
    Akele, el bloque es un <div> con exactamente 3 <p> hijos directos:
    el dorsal ("#45"), un separador ("•") y la posición ("Ala-Pivot")."""
    soup = BeautifulSoup(html, "html.parser")
    for contenedor in soup.find_all("div"):
        hijos = contenedor.find_all("p", recursive=False)
        if len(hijos) != 3:
            continue
        if not hijos[0].get_text(strip=True).startswith("#"):
            continue
        texto_posicion = hijos[2].get_text(strip=True)
        posicion = _POSICIONES_WEB.get(texto_posicion.lower())
        if posicion is None:
            print(f"  [aviso] posición '{texto_posicion}' de la ficha no reconocida - se ignora.")
            return None
        return posicion
    return None


def diagnosticar(url: str) -> None:
    """Pensada para ejecutarse en el ordenador del usuario (ver docstring
    del módulo). Descarga la URL y comprueba si el HTML CRUDO (antes de
    cualquier hidratación por JavaScript) ya contiene la tabla de
    estadísticas, para confirmar que es scrapeable con requests+BeautifulSoup
    sin necesidad de un navegador real."""
    print(f"Descargando {url} ...")
    html = obtener_html_ficha(url)
    if html is None:
        print("No se pudo descargar nada - ver aviso de arriba.")
        return
    print(f"OK, {len(html)} caracteres descargados.")
    if "colGroup" not in html:
        print(
            "[problema] El HTML descargado NO contiene ninguna clase "
            "'colGroup' - la tabla de estadísticas no viene en el HTML "
            "crudo (puede que se inyecte luego por JavaScript, o que esta "
            "respuesta sea una página de bloqueo/error distinta a la "
            "esperada). Revisa manualmente el contenido descargado."
        )
        return
    if "Temporada" not in html:
        print(
            "[aviso] Hay clases 'colGroup' pero no se encontró la palabra "
            "'Temporada' - puede que el idioma de la URL no sea 'es' o que "
            "la estructura haya cambiado."
        )
        return
    filas = parsear_tabla_temporadas(html)
    print(f"¡Tabla encontrada y parseada! {len(filas)} fila(s) de temporada real detectadas:")
    for fila in filas:
        print(f"  {fila['temporada']} ({fila['codigo_equipo']}): "
              f"{fila['partidos_jugados']} PJ, {fila['puntos_totales']} pts, PIR {fila['valoracion_pir_total']}")


def _localizar_bloque_tabla(soup: BeautifulSoup) -> list:
    """Devuelve la lista de colGroups (en orden) desde el que tiene
    'Temporada' en su cabecera hasta el que tiene 'PIR' (inclusive).
    Lista vacía si no se encuentra."""
    colgroups = soup.find_all("div", class_=lambda c: c and "colGroup" in c)
    idx_temporada = None
    idx_pir = None
    for idx, cg in enumerate(colgroups):
        if idx_temporada is None:
            if "Temporada" in cg.get_text(" ", strip=True):
                idx_temporada = idx
            continue
        # buscamos una fila cuyo texto sea EXACTAMENTE "PIR" (cabecera), no solo que la contenga
        if any(f.get_text(strip=True) == "PIR" for f in _filas_de(cg)):
            idx_pir = idx
            break
    if idx_temporada is None or idx_pir is None:
        return []
    return colgroups[idx_temporada:idx_pir + 1]


def _filas_de(colgroup) -> list:
    """Filas (hijas directas) de un colGroup - no recursivo, para no
    confundir con ningún div anidado dentro de una celda."""
    return colgroup.find_all("div", class_=lambda c: c and "__row" in c, recursive=False)


def _a_min_decimal(texto: str) -> Optional[float]:
    """'195:26' (mm:ss) -> minutos decimales."""
    if not texto or ":" not in texto:
        return None
    minutos, segundos = texto.split(":")
    try:
        return round(int(minutos) + int(segundos) / 60, 2)
    except ValueError:
        return None


def _con_int(texto: str) -> tuple[Optional[int], Optional[int]]:
    """'22/28' -> (22, 28)."""
    if not texto or "/" not in texto:
        return None, None
    con, intentados = texto.split("/", 1)
    try:
        return int(con), int(intentados)
    except ValueError:
        return None, None


def _entero(texto: str) -> Optional[int]:
    try:
        return int(texto)
    except (TypeError, ValueError):
        return None


def _decimal(texto: str) -> Optional[float]:
    try:
        return float(texto.replace(",", "."))
    except (TypeError, ValueError):
        return None


def parsear_tabla_temporadas(html: str) -> list[dict]:
    """Devuelve una lista de diccionarios, uno por temporada REAL (excluye
    'Total'/'Media', ver parsear_carrera_euroleague()). Cada diccionario
    trae totales reales (no estimados) más 'codigo_temporada_api'
    (p.ej. 'E2018') y 'codigo_equipo' (p.ej. 'OLY') para poder resolver el
    equipo con scraping.euroleague_api.obtener_clubes()."""
    soup = BeautifulSoup(html, "html.parser")
    bloque = _localizar_bloque_tabla(soup)
    if not bloque:
        print("[aviso] No se encontró la tabla de temporadas en el HTML (¿estructura cambiada?).")
        return []

    filas_por_colgroup = [_filas_de(cg) for cg in bloque]
    n_filas = len(filas_por_colgroup[0])

    registros = []
    for i in range(2, n_filas - 2):  # 0=separador, 1=cabecera, últimas 2=Total/Media
        fila_temporada = filas_por_colgroup[0][i]
        boton = fila_temporada.find("button")
        if boton is None or not boton.get("data-season-code"):
            continue  # fila inesperada, no es una temporada real
        codigo_temporada_api = boton["data-season-code"]
        if not _PATRON_CODIGO_TEMPORADA.match(codigo_temporada_api):
            # Visto en jugadores con participaciones en torneos/eventos
            # especiales (p.ej. 'TBO25', 'TF424', 'TM24' - no son
            # temporadas de liga regular, sino algún torneo clasificatorio
            # o exhibición) que la ficha mezcla en la misma tabla. No
            # siguen el formato letra+año de una temporada real, así que
            # no se pueden resolver ni guardar como tal - se descarta esa
            # fila sin más (no es un error del jugador, es un tipo de fila
            # que este módulo no cubre).
            print(f"  [aviso] fila de temporada con código no estándar '{codigo_temporada_api}' "
                  f"(torneo/evento especial, no temporada de liga) - se omite.")
            continue
        codigo_equipo = boton.get("data-team-code")
        temporada_visible = boton.get_text(strip=True)

        g_gs = [c.get_text(strip=True) for c in filas_por_colgroup[1][i].find_all("div")]
        min_pts_tiros = [c.get_text(strip=True) for c in filas_por_colgroup[2][i].find_all("div")]
        rebotes = [c.get_text(strip=True) for c in filas_por_colgroup[3][i].find_all("div")]
        ast_rob_per = [c.get_text(strip=True) for c in filas_por_colgroup[4][i].find_all("div")]
        bloqueos = [c.get_text(strip=True) for c in filas_por_colgroup[5][i].find_all("div")]
        faltas = [c.get_text(strip=True) for c in filas_por_colgroup[6][i].find_all("div")]
        pir = [c.get_text(strip=True) for c in filas_por_colgroup[7][i].find_all("div")]

        t2_con, t2_int = _con_int(min_pts_tiros[2]) if len(min_pts_tiros) > 2 else (None, None)
        t3_con, t3_int = _con_int(min_pts_tiros[3]) if len(min_pts_tiros) > 3 else (None, None)
        tl_con, tl_int = _con_int(min_pts_tiros[4]) if len(min_pts_tiros) > 4 else (None, None)

        registros.append({
            "temporada_visible": temporada_visible,
            "codigo_temporada_api": codigo_temporada_api,
            "codigo_equipo": codigo_equipo,
            "temporada": temporada_texto(int(codigo_temporada_api[1:])),
            "partidos_jugados": _entero(g_gs[0]) if len(g_gs) > 0 else None,
            "partidos_titular": _entero(g_gs[1]) if len(g_gs) > 1 else None,
            "minutos_totales": _a_min_decimal(min_pts_tiros[0]) if len(min_pts_tiros) > 0 else None,
            "puntos_totales": _entero(min_pts_tiros[1]) if len(min_pts_tiros) > 1 else None,
            "t2_convertidos": t2_con, "t2_intentados": t2_int,
            "t3_convertidos": t3_con, "t3_intentados": t3_int,
            "tl_convertidos": tl_con, "tl_intentados": tl_int,
            "rebotes_ofensivos_totales": _entero(rebotes[0]) if len(rebotes) > 0 else None,
            "rebotes_defensivos_totales": _entero(rebotes[1]) if len(rebotes) > 1 else None,
            "rebotes_totales": _entero(rebotes[2]) if len(rebotes) > 2 else None,
            "asistencias_totales": _entero(ast_rob_per[0]) if len(ast_rob_per) > 0 else None,
            "robos_totales": _entero(ast_rob_per[1]) if len(ast_rob_per) > 1 else None,
            "perdidas_totales": _entero(ast_rob_per[2]) if len(ast_rob_per) > 2 else None,
            "tapones_totales": _entero(bloqueos[0]) if len(bloqueos) > 0 else None,
            "tapones_recibidos_totales": _entero(bloqueos[1]) if len(bloqueos) > 1 else None,
            "faltas_totales": _entero(faltas[0]) if len(faltas) > 0 else None,
            "faltas_recibidas_totales": _entero(faltas[1]) if len(faltas) > 1 else None,
            "valoracion_pir_total": _entero(pir[0]) if len(pir) > 0 else None,
        })
    return registros


def parsear_carrera_euroleague(html: str) -> dict[str, dict]:
    """Agregados de carrera ('Total'/'Media') de la tabla de temporadas,
    en el MISMO formato de claves que scraping.estadisticas.parsear_carrera
    (para poder reutilizar guardar_estadisticas_carrera tal cual). 'Media'
    trae promedios reales de la fuente; 'Total' trae sumas reales."""
    soup = BeautifulSoup(html, "html.parser")
    bloque = _localizar_bloque_tabla(soup)
    if not bloque:
        return {}
    filas_por_colgroup = [_filas_de(cg) for cg in bloque]
    n_filas = len(filas_por_colgroup[0])

    carrera = {}
    for i, etiqueta_bd in ((n_filas - 2, "Totales"), (n_filas - 1, "Promedios")):
        g_gs = [c.get_text(strip=True) for c in filas_por_colgroup[1][i].find_all("div")]
        min_pts_tiros = [c.get_text(strip=True) for c in filas_por_colgroup[2][i].find_all("div")]
        rebotes = [c.get_text(strip=True) for c in filas_por_colgroup[3][i].find_all("div")]
        ast_rob_per = [c.get_text(strip=True) for c in filas_por_colgroup[4][i].find_all("div")]
        bloqueos = [c.get_text(strip=True) for c in filas_por_colgroup[5][i].find_all("div")]
        faltas = [c.get_text(strip=True) for c in filas_por_colgroup[6][i].find_all("div")]
        pir = [c.get_text(strip=True) for c in filas_por_colgroup[7][i].find_all("div")]

        es_media = etiqueta_bd == "Promedios"
        numero = _decimal if es_media else _entero
        t2_con, t2_int, t2_pct = (None, None, None)
        t3_con, t3_int, t3_pct = (None, None, None)
        tl_con, tl_int, tl_pct = (None, None, None)
        if es_media:
            # en 'Media' los tiros vienen como porcentaje ("63.3%"), no con/int
            t2_pct = _decimal((min_pts_tiros[2] or "").replace("%", "")) if len(min_pts_tiros) > 2 else None
            t3_pct = _decimal((min_pts_tiros[3] or "").replace("%", "")) if len(min_pts_tiros) > 3 else None
            tl_pct = _decimal((min_pts_tiros[4] or "").replace("%", "")) if len(min_pts_tiros) > 4 else None
        else:
            t2_con, t2_int = _con_int(min_pts_tiros[2]) if len(min_pts_tiros) > 2 else (None, None)
            t3_con, t3_int = _con_int(min_pts_tiros[3]) if len(min_pts_tiros) > 3 else (None, None)
            tl_con, tl_int = _con_int(min_pts_tiros[4]) if len(min_pts_tiros) > 4 else (None, None)

        carrera[etiqueta_bd] = {
            "partidos_jugados": _entero(g_gs[0]) if len(g_gs) > 0 else None,
            "cinco_iniciales": numero(g_gs[1]) if len(g_gs) > 1 else None,
            # el nombre de la clave es heredado del esquema de ACB (ver
            # scraping/estadisticas.py): contiene el TOTAL real cuando
            # etiqueta_bd == "Totales" y el PROMEDIO real cuando es
            # "Promedios" - igual que pasa con 'puntos_promedio' más abajo.
            "minutos_promedio": _a_min_decimal(min_pts_tiros[0]) if len(min_pts_tiros) > 0 else None,
            "puntos_promedio": numero(min_pts_tiros[1]) if len(min_pts_tiros) > 1 else None,
            "puntos_max": None,
            "t2_con": t2_con, "t2_int": t2_int, "t2_pct": t2_pct,
            "t3_con": t3_con, "t3_int": t3_int, "t3_pct": t3_pct,
            "tl_con": tl_con, "tl_int": tl_int, "tl_pct": tl_pct,
            "rebotes_ofe": numero(rebotes[0]) if len(rebotes) > 0 else None,
            "rebotes_def": numero(rebotes[1]) if len(rebotes) > 1 else None,
            "rebotes_promedio": numero(rebotes[2]) if len(rebotes) > 2 else None,
            "asistencias_promedio": numero(ast_rob_per[0]) if len(ast_rob_per) > 0 else None,
            "recuperaciones_promedio": numero(ast_rob_per[1]) if len(ast_rob_per) > 1 else None,
            "perdidas_promedio": numero(ast_rob_per[2]) if len(ast_rob_per) > 2 else None,
            "tapones_favor": numero(bloqueos[0]) if len(bloqueos) > 0 else None,
            "tapones_contra": numero(bloqueos[1]) if len(bloqueos) > 1 else None,
            "mates": None,
            "faltas_cometidas": numero(faltas[0]) if len(faltas) > 0 else None,
            "faltas_recibidas": numero(faltas[1]) if len(faltas) > 1 else None,
            "mas_menos": None,
            "valoracion_pir": numero(pir[0]) if len(pir) > 0 else None,
            "victorias": None, "derrotas": None,
        }
    return carrera


def guardar_estadisticas_temporada_euroleague(jugador_id: int, competicion: str, registro: dict) -> None:
    """Inserta/actualiza estadisticas_temporada con los TOTALES reales de
    euroleaguebasketball.net (no estimados, a diferencia de ACB). El
    equipo debe resolverse ANTES de llamar a esto (ver
    actualizar_estadisticas_jugador) y pasarse ya en registro['equipo_id']."""
    partidos = registro.get("partidos_jugados") or 0

    def _pct(con, intentos):
        if not con or not intentos:
            return None
        return round(con / intentos * 100, 1)

    def _prom(total):
        if total is None or not partidos:
            return None
        return round(total / partidos, 2)

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO estadisticas_temporada
                (jugador_id, equipo_id, temporada, competicion,
                 partidos_jugados, partidos_titular,
                 minutos_totales, minutos_promedio,
                 puntos_totales, puntos_promedio, puntos_max,
                 t2_convertidos, t2_intentados, t3_convertidos, t3_intentados,
                 tl_convertidos, tl_intentados,
                 rebotes_totales, rebotes_promedio,
                 rebotes_ofensivos_totales, rebotes_defensivos_totales,
                 asistencias_totales, asistencias_promedio,
                 robos_totales, tapones_totales, tapones_recibidos_totales,
                 mates_totales, perdidas_totales,
                 faltas_totales, faltas_recibidas_totales,
                 porcentaje_tiro2, porcentaje_tiro3, porcentaje_tiro_libre,
                 mas_menos_promedio, valoracion_pir, victorias, derrotas, fuente_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    (SELECT id FROM fuentes WHERE nombre = 'Scraping'))
            ON CONFLICT(jugador_id, equipo_id, temporada, competicion)
            DO UPDATE SET
                partidos_jugados = excluded.partidos_jugados,
                partidos_titular = excluded.partidos_titular,
                minutos_totales = excluded.minutos_totales,
                minutos_promedio = excluded.minutos_promedio,
                puntos_totales = excluded.puntos_totales,
                puntos_promedio = excluded.puntos_promedio,
                puntos_max = excluded.puntos_max,
                t2_convertidos = excluded.t2_convertidos,
                t2_intentados = excluded.t2_intentados,
                t3_convertidos = excluded.t3_convertidos,
                t3_intentados = excluded.t3_intentados,
                tl_convertidos = excluded.tl_convertidos,
                tl_intentados = excluded.tl_intentados,
                rebotes_totales = excluded.rebotes_totales,
                rebotes_promedio = excluded.rebotes_promedio,
                rebotes_ofensivos_totales = excluded.rebotes_ofensivos_totales,
                rebotes_defensivos_totales = excluded.rebotes_defensivos_totales,
                asistencias_totales = excluded.asistencias_totales,
                asistencias_promedio = excluded.asistencias_promedio,
                robos_totales = excluded.robos_totales,
                tapones_totales = excluded.tapones_totales,
                tapones_recibidos_totales = excluded.tapones_recibidos_totales,
                mates_totales = excluded.mates_totales,
                perdidas_totales = excluded.perdidas_totales,
                faltas_totales = excluded.faltas_totales,
                faltas_recibidas_totales = excluded.faltas_recibidas_totales,
                porcentaje_tiro2 = excluded.porcentaje_tiro2,
                porcentaje_tiro3 = excluded.porcentaje_tiro3,
                porcentaje_tiro_libre = excluded.porcentaje_tiro_libre,
                mas_menos_promedio = excluded.mas_menos_promedio,
                valoracion_pir = excluded.valoracion_pir,
                victorias = excluded.victorias,
                derrotas = excluded.derrotas,
                fuente_id = excluded.fuente_id,
                fecha_actualizacion = datetime('now');
            """,
            (
                jugador_id, registro["equipo_id"], registro["temporada"], competicion,
                registro.get("partidos_jugados"), registro.get("partidos_titular"),
                registro.get("minutos_totales"), _prom(registro.get("minutos_totales")),
                registro.get("puntos_totales"), _prom(registro.get("puntos_totales")), None,
                registro.get("t2_convertidos"), registro.get("t2_intentados"),
                registro.get("t3_convertidos"), registro.get("t3_intentados"),
                registro.get("tl_convertidos"), registro.get("tl_intentados"),
                registro.get("rebotes_totales"), _prom(registro.get("rebotes_totales")),
                registro.get("rebotes_ofensivos_totales"), registro.get("rebotes_defensivos_totales"),
                registro.get("asistencias_totales"), _prom(registro.get("asistencias_totales")),
                registro.get("robos_totales"), registro.get("tapones_totales"),
                registro.get("tapones_recibidos_totales"), None,
                registro.get("perdidas_totales"),
                registro.get("faltas_totales"), registro.get("faltas_recibidas_totales"),
                _pct(registro.get("t2_convertidos"), registro.get("t2_intentados")),
                _pct(registro.get("t3_convertidos"), registro.get("t3_intentados")),
                _pct(registro.get("tl_convertidos"), registro.get("tl_intentados")),
                None, _prom(registro.get("valoracion_pir_total")), None, None,
            ),
        )


def _buscar_por_tv_code(clubes: dict, codigo: str) -> Optional[dict]:
    """Busca un club por su 'tv_code' (ver scraping/euroleague_api.obtener_clubes)
    cuando no se encuentra directamente por 'code' (ni por _ALIAS_CODIGO_CLUB).

    CONFIRMADO el 2026-10-04 contra la API real (temporadas E2026/U2026 y
    E2020, comparando con el reparto fusionar/renombrar de
    reconciliar_clubes_provisionales.py): el atributo data-team-code de la
    ficha de estadísticas usa 'tvCode', NO 'code' - son bastante distintos
    en muchos clubes (Fenerbahce 'code'='ULK' pero 'tvCode'='FNB'; Baskonia
    'BAS'/'KBA'; Olimpia Milano en 2020-21 'MIL'/'AXM'...). Esto explicaba
    la mayoría de los códigos que antes quedaban "sin mapeo" en
    MAPEO_CODIGOS - se resuelven aquí directamente, sin necesidad de
    mantenerlos a mano. Recorrido lineal simple: la lista de clubes de una
    temporada es pequeña (unas pocas decenas)."""
    for info in clubes.values():
        if info.get("tv_code") == codigo:
            return info
    return None


def _obtener_clubes_seguro(codigo_competicion: str, codigo_temp_api: str) -> dict:
    """Como obtener_clubes(), pero nunca lanza: un fallo de red aquí (visto
    en el backfill masivo - miles de peticiones repetidas a la misma API
    sin caché entre jugadores pueden disparar timeouts intermitentes) no
    debe tirar abajo el procesamiento de esa fila - simplemente no se
    podrá resolver el club y se cae al nombre provisional (ver
    actualizar_estadisticas_jugador)."""
    try:
        return obtener_clubes(codigo_competicion, codigo_temp_api)
    except requests.RequestException as error:
        print(f"  [aviso] no se pudo obtener la lista de clubes de {codigo_temp_api}: {error}")
        return {}


def actualizar_estadisticas_jugador(jugador_id: int, nombre: str, apellidos: str, id_externo: str,
                                     codigo_competicion: str, cache_clubes: Optional[dict] = None) -> int:
    """Descarga y guarda las estadísticas de temporada + carrera de un
    jugador para una competición ('E' o 'U'). Devuelve el número de
    temporadas guardadas (0 si falló la descarga o no se encontró tabla).

    cache_clubes: diccionario {codigo_temporada_api: {codigo_club: info}}
    opcional, pensado para COMPARTIRSE entre llamadas a esta función para
    distintos jugadores (ver scraping/actualizar_estadisticas_euroleague.py)
    - evita pedir la misma temporada a la API una vez por cada jugador que
    jugó en ella. Si no se pasa, se usa uno nuevo solo para esta llamada
    (comportamiento anterior, más lento en un backfill masivo)."""
    competicion = _NOMBRE_COMPETICION_POR_CODIGO[codigo_competicion]
    url = url_ficha_jugador(codigo_competicion, nombre, apellidos, id_externo)
    html = obtener_html_ficha(url)
    if html is None:
        return 0

    actualizar_posicion_jugador(jugador_id, extraer_posicion(html))

    temporadas = parsear_tabla_temporadas(html)
    if not temporadas:
        return 0

    if cache_clubes is None:
        cache_clubes = {}
    guardadas = 0
    for fila in temporadas:
        codigo_temp_api = fila["codigo_temporada_api"]
        if codigo_temp_api not in cache_clubes:
            # OJO: la competición de la llamada a la API de clubes debe ser
            # la del PROPIO código de temporada de esta fila (su primera
            # letra, 'E' o 'U' - ver _PATRON_CODIGO_TEMPORADA), NO la
            # 'codigo_competicion' de esta función (la ficha/URL que se
            # está procesando). Confirmado el 2026-10-04: una misma ficha
            # (tanto si se pide en versión Euroliga como EuroCup) trae
            # filas de AMBAS competiciones mezcladas en la misma tabla -
            # si aquí se usara 'codigo_competicion' a secas, una fila de
            # temporada 'U2026' procesada mientras se mira la ficha 'E'
            # pediría .../competitions/E/seasons/U2026/clubs (sin
            # sentido, no devuelve nada) y, como cache_clubes se COMPARTE
            # entre jugadores por rendimiento, ese resultado vacío se
            # quedaba cacheado para siempre bajo la clave 'U2026' - de ahí
            # que algunos códigos (COL, URV, JLB, UNI, BLK, MSB, TTA, CHE,
            # PBC, BKS...) seguían fallando SIEMPRE en el backfill aunque
            # ya se hubiera añadido el fallback por tv_code.
            cache_clubes[codigo_temp_api] = _obtener_clubes_seguro(codigo_temp_api[0], codigo_temp_api)
        codigo_club = fila["codigo_equipo"]
        club_info = cache_clubes[codigo_temp_api].get(codigo_club) \
            or cache_clubes[codigo_temp_api].get(_ALIAS_CODIGO_CLUB.get(codigo_club)) \
            or _buscar_por_tv_code(cache_clubes[codigo_temp_api], codigo_club)
        if club_info is None:
            # El código de club de la ficha de estadísticas no aparece en
            # la API de clubes de esa temporada (visto sobre todo en
            # temporadas antiguas - probablemente el club cambió de código
            # con el tiempo y la API solo expone el vigente). Para no
            # perder las estadísticas de esa temporada, se guarda con el
            # propio código como nombre de equipo PROVISIONAL (sin país) -
            # quedará como un equipo con nombre en mayúsculas de 3 letras,
            # fácil de localizar luego para fusionarlo con el nombre real
            # una vez identificado.
            print(f"  [aviso] club '{fila['codigo_equipo']}' no encontrado en la API para la temporada "
                  f"{codigo_temp_api} - se guarda con nombre provisional '{fila['codigo_equipo']}'.")
            nombre_equipo, pais_equipo = fila["codigo_equipo"], None
        else:
            nombre_equipo, pais_equipo = club_info["nombre"], club_info["pais"]
        equipo_id = obtener_o_crear_equipo(nombre_equipo, competicion=competicion, pais=pais_equipo)
        fila["equipo_id"] = equipo_id
        guardar_estadisticas_temporada_euroleague(jugador_id, competicion, fila)
        guardadas += 1

    carrera = parsear_carrera_euroleague(html)
    for tipo_fila, registro in carrera.items():
        guardar_estadisticas_carrera(jugador_id, tipo_fila, registro, competicion=competicion)

    return guardadas


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Estadísticas de Euroliga/EuroCup desde euroleaguebasketball.net.")
    sub = parser.add_subparsers(dest="accion", required=True)

    p_diag = sub.add_parser("diagnosticar", help="Comprueba si se puede descargar/parsear una ficha de jugador.")
    p_diag.add_argument("id_externo", help="Código numérico del jugador, p.ej. 003469")
    p_diag.add_argument("nombre_apellidos_slug", help="Slug nombre-apellidos, p.ej. vezenkov-sasha (apellido primero)")
    p_diag.add_argument("codigo_competicion", choices=["E", "U"])

    args = parser.parse_args()
    if args.accion == "diagnosticar":
        url = f"{_PREFIJO_URL}/es/{_RUTA_COMPETICION[args.codigo_competicion]}/players/{args.nombre_apellidos_slug}/{args.id_externo}/"
        diagnosticar(url)
