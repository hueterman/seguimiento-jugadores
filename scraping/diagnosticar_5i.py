"""
Diagnóstico puntual: muestra el valor crudo (antes de convertir) que
pandas extrae de la columna "5i" para cada fila (temporadas + Totales +
Promedios), para entender por qué esa columna se comporta distinto según
la fila.

Uso:
    python -m scraping.diagnosticar_5i <slug_acb> [--edition-id 90]
"""
import argparse

from scraping.base_scraper import crear_sesion, obtener_html
from scraping.estadisticas import _tabla_temporadas_normalizada, _url_temporadas


def diagnosticar(slug_jugador: str, edition_id: int = 90) -> None:
    sesion = crear_sesion()
    html = obtener_html(sesion, _url_temporadas(slug_jugador, edition_id))
    if html is None:
        print("No se pudo descargar la página.")
        return

    tabla = _tabla_temporadas_normalizada(html)
    if tabla is None:
        print("No se pudo localizar/normalizar la tabla (revisa el aviso de columnas).")
        return

    columna = tabla["cinco_iniciales"]
    print(f"dtype de la columna 'cinco_iniciales': {columna.dtype}\n")
    print(f"{'temporada':<12} {'valor crudo':<20} {'tipo python'}")
    for temporada, valor in zip(tabla["temporada"], columna):
        print(f"{str(temporada):<12} {repr(valor):<20} {type(valor).__name__}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("slug_acb")
    parser.add_argument("--edition-id", type=int, default=90)
    args = parser.parse_args()
    diagnosticar(args.slug_acb, edition_id=args.edition_id)
