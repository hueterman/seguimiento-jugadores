"""
Diagnóstico puntual: para un jugador cuyo scraper de temporadas encuentra 0
resultados, descarga la página de temporadas y muestra qué ve realmente
pandas (cuántas tablas, su forma, y si alguna tiene una fila "Totales"),
en vez de asumir silenciosamente que no hay datos.

Uso:
    python -m scraping.diagnosticar_temporada <slug_acb> [--edition-id 90]
"""
import argparse
import io

import pandas as pd

from scraping.base_scraper import crear_sesion, obtener_html
from scraping.estadisticas import _url_temporadas


def diagnosticar(slug_jugador: str, edition_id: int = 90) -> None:
    url = _url_temporadas(slug_jugador, edition_id)
    print(f"URL: {url}\n")

    sesion = crear_sesion()
    html = obtener_html(sesion, url)
    if html is None:
        print("No se pudo descargar la página (ver errores de arriba, si los hay).")
        return

    print(f"HTML descargado: {len(html)} caracteres.\n")

    try:
        tablas = pd.read_html(io.StringIO(html), header=[0, 1], thousands=None)
    except ValueError as error:
        print(f"pandas.read_html no encontró ninguna tabla: {error}")
        print("\n¿Contiene la página la palabra 'Totales'? ->", "Totales" in html)
        print("¿Contiene la página la palabra 'temporada'? ->", "temporada" in html.lower())
        return

    print(f"pandas encontró {len(tablas)} tabla(s) en la página.\n")
    for indice, tabla in enumerate(tablas):
        primera_columna = tabla.iloc[:, 0].astype(str).str.strip().str.lower() if tabla.shape[1] else None
        tiene_totales = bool((primera_columna == "totales").any()) if primera_columna is not None else False
        print(f"--- Tabla {indice}: forma {tabla.shape} - ¿tiene fila 'Totales'? {tiene_totales} ---")
        print(tabla.head(10))
        print()

    if not any(
        bool((t.iloc[:, 0].astype(str).str.strip().str.lower() == "totales").any())
        for t in tablas if t.shape[1]
    ):
        print(
            "Ninguna tabla tiene una fila 'Totales' en la primera columna - por "
            "eso el scraper normal encuentra 0 temporadas/0 carrera para este "
            "jugador. Puede ser que acb.com aún no tenga publicadas sus "
            "estadísticas bajo esta edición/equipo."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("slug_acb")
    parser.add_argument("--edition-id", type=int, default=90)
    args = parser.parse_args()
    diagnosticar(args.slug_acb, edition_id=args.edition_id)
