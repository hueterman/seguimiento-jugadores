"""
Utilidades comunes para los scrapers de estadísticas y trayectoria.
"""
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

DEFAULT_HEADERS = {
    # Confirmado el 2026-10-03: con un User-Agent de bot básico, acb.com
    # devuelve la página de plantilla de un equipo SIN la sección "Cuerpo
    # técnico" (el resto del contenido sí llega completo). Con cabeceras
    # de navegador real (probado con Chrome vía el puente al PC del
    # usuario) esa sección SÍ aparece, sin necesidad de ejecutar
    # JavaScript - así que el problema no era "la página se carga por
    # JS", sino que el servidor sirve una versión reducida a bots. Si en
    # el futuro vuelve a faltar algo, lo primero a revisar es si el sitio
    # ha empezado a filtrar por alguna otra cabecera.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}


def crear_sesion() -> requests.Session:
    sesion = requests.Session()
    sesion.headers.update(DEFAULT_HEADERS)
    return sesion


def obtener_html(sesion: requests.Session, url: str, espera_seg: float = 1.0,
                  reintentos: int = 3) -> Optional[str]:
    """Descarga una URL con reintentos y una pequeña espera entre peticiones."""
    for intento in range(1, reintentos + 1):
        try:
            respuesta = sesion.get(url, timeout=10)
            respuesta.raise_for_status()
            time.sleep(espera_seg)
            return respuesta.text
        except requests.RequestException as error:
            print(f"[intento {intento}/{reintentos}] Error al pedir {url}: {error}")
            time.sleep(espera_seg * intento)
    return None


def parsear_tabla(html: str, selector_tabla: str) -> list[dict]:
    """
    Convierte una tabla HTML (con fila de cabeceras) en una lista de
    diccionarios {cabecera: valor}. Punto de partida genérico.
    """
    soup = BeautifulSoup(html, "html.parser")
    tabla = soup.select_one(selector_tabla)
    if tabla is None:
        return []

    filas = tabla.find_all("tr")
    if not filas:
        return []

    cabeceras = [celda.get_text(strip=True) for celda in filas[0].find_all(["th", "td"])]
    datos = []
    for fila in filas[1:]:
        celdas = [celda.get_text(strip=True) for celda in fila.find_all("td")]
        if len(celdas) == len(cabeceras):
            datos.append(dict(zip(cabeceras, celdas)))
    return datos
