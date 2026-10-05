"""
Scraper de estadísticas por temporada de un jugador, a partir de la página
"Temporadas" de acb.com:
    https://acb.com/es/liga/jugadores/<slug>/temporada?editionId=<id>

Estructura CONFIRMADA sobre un jugador real (Luka Bozic, slug
"luka-bozic-30003420", editionId=90): la tabla trae una fila por temporada
más "Totales" y "Promedios" (agregados de carrera) al final, con cabecera
en dos niveles — p.ej. "Puntos" se divide en "Tot"/"Max". Un solo request a
esta URL devuelve el HISTORIAL COMPLETO del jugador (no hace falta repetir
la petición por temporada).

pandas.read_html reconstruye ese encabezado de dos niveles directamente a
partir de los <table>/colspan reales, así que no depende de nombres de
clase CSS. El parseo se ha probado contra un fixture que reproduce la
tabla exacta observada, con resultados que cuadran con los promedios
publicados en la ficha del jugador.

Notas conocidas / pendientes:
- La columna "5i" no se ha podido identificar con certeza (¿quintetos
  iniciales?) — se guarda tal cual en el resultado pero no se usa al
  guardar en la BD.
- La tabla de acb.com da promedios por partido, no totales de temporada
  (salvo partidos jugados). Los campos "_totales" de robos/tapones/
  pérdidas/faltas se ESTIMAN como promedio × partidos_jugados, redondeado
  — no son el dato exacto de la fuente.
"""
import io
import re
from typing import Optional

import pandas as pd

from db.conexion import get_connection, obtener_o_crear_equipo
from scraping.base_scraper import crear_sesion, obtener_html

COLUMNAS = [
    "temporada", "club", "partidos_jugados", "minutos_promedio", "cinco_iniciales",
    "puntos_promedio", "puntos_max",
    "t3_con", "t3_int", "t3_pct",
    "t2_con", "t2_int", "t2_pct",
    "tl_con", "tl_int", "tl_pct",
    "rebotes_ofe", "rebotes_def", "rebotes_promedio",
    "asistencias_promedio",
    "recuperaciones_promedio", "perdidas_promedio",
    "tapones_favor", "tapones_contra",
    "mates",
    "faltas_cometidas", "faltas_recibidas",
    "mas_menos", "valoracion_pir", "victorias", "derrotas",
]


def _url_temporadas(slug_jugador: str, edition_id: int = 90) -> str:
    return f"https://acb.com/es/liga/jugadores/{slug_jugador}/temporada?editionId={edition_id}"


_PATRON_MILES = re.compile(r"^-?\d{1,3}(\.\d{3})+$")


def _a_numero(valor) -> Optional[float]:
    """Convierte '16,2' / '0.9' / '33,3%' / '29:10' (mm:ss) / '1.260'
    (miles) a float; None si no se puede.

    acb.com no es 100% consistente: la mayoría de columnas usan coma
    decimal ("16,2"), pero al menos "5i" usa punto decimal ("0.9") -
    probablemente porque pandas infiere esas celdas como numéricas al
    vuelo. Los totales de carrera grandes SÍ usan el punto como separador
    de miles ("1.260" = 1260). Para no confundir un decimal con punto
    ("0.9") con miles ("1.260"), solo se trata como separador de miles
    cuando el texto encaja EXACTAMENTE con el patrón de agrupación de
    miles (grupos de 3 dígitos tras el punto, sin parte decimal final) -
    un decimal real como "0.9" o "16.2" nunca tiene esa forma.
    """
    if valor is None:
        return None
    texto = str(valor).strip().replace("%", "")
    if texto in ("", "-", "nan", "None"):
        return None
    if ":" in texto:  # minutos en formato mm:ss -> minutos decimales
        minutos, segundos = texto.split(":")
        try:
            return round(int(minutos) + int(segundos) / 60, 2)
        except ValueError:
            return None
    if _PATRON_MILES.match(texto):
        texto = texto.replace(".", "")
    # coma decimal española; si no hay coma, puede ser un entero normal
    # o ya un decimal con punto (ver docstring)
    texto = texto.replace(",", ".") if texto.count(",") == 1 else texto.replace(",", "")
    try:
        return float(texto)
    except ValueError:
        return None


def _normalizar_temporada(codigo: str) -> str:
    """'25-26' -> '2025-2026'. Asume siglo 2000 (ajustar si hace falta cubrir <2000)."""
    match = re.match(r"^(\d{2})-(\d{2})$", codigo.strip())
    if not match:
        return codigo.strip()
    inicio, fin = match.groups()
    return f"20{inicio}-20{fin}"


def _localizar_tabla_temporadas(tablas: list[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """Heurística: acb.com repite una tabla-plantilla vacía antes de la tabla
    real. En vez de fiarnos del nº de columnas (que puede no coincidir con lo
    asumido en COLUMNAS), nos quedamos con la tabla que tenga una fila
    'Totales' en la primera columna - es la marca fiable de que es la tabla
    con datos, da igual cuántas columnas tenga."""
    candidatas = []
    for tabla in tablas:
        if tabla.shape[1] == 0 or tabla.shape[0] == 0:
            continue
        primera_columna = tabla.iloc[:, 0].astype(str).str.strip().str.lower()
        if (primera_columna == "totales").any():
            candidatas.append(tabla)
    if not candidatas:
        return None
    # Si hubiera más de una candidata, nos quedamos con la más completa.
    return max(candidatas, key=lambda t: t.shape[1])


def _tabla_temporadas_normalizada(html: str) -> Optional[pd.DataFrame]:
    """Localiza y valida la tabla de temporadas, con las columnas ya
    renombradas a COLUMNAS. None si no se encuentra o no se puede mapear
    con garantías (y en ese caso ya avisa por consola del motivo)."""
    tablas = pd.read_html(io.StringIO(html), header=[0, 1], thousands=None)
    tabla = _localizar_tabla_temporadas(tablas)
    if tabla is None:
        return None

    if tabla.shape[1] != len(COLUMNAS):
        print(
            f"[aviso] La tabla de temporadas tiene {tabla.shape[1]} columnas "
            f"y se esperaban {len(COLUMNAS)}. No se puede mapear con garantías "
            f"- cabecera real detectada por pandas:"
        )
        for columna in tabla.columns:
            print(f"    {columna}")
        print(
            "Copia este aviso y la lista de columnas y lo ajustamos en "
            "scraping/estadisticas.py (lista COLUMNAS)."
        )
        return None

    tabla.columns = COLUMNAS
    return tabla


def parsear_temporadas(html: str) -> list[dict]:
    """
    Devuelve una lista de diccionarios, uno por temporada real del jugador
    (excluye las filas 'Totales' y 'Promedios', que son agregados de
    carrera - ver parsear_carrera()).
    """
    tabla = _tabla_temporadas_normalizada(html)
    if tabla is None:
        return []

    registros = []
    for _, fila in tabla.iterrows():
        temporada_cruda = str(fila["temporada"]).strip()
        if temporada_cruda.lower() in ("totales", "promedios", "nan"):
            continue
        registro = {
            "temporada": _normalizar_temporada(temporada_cruda),
            "club": str(fila["club"]).strip(),
        }
        for columna in COLUMNAS[2:]:
            registro[columna] = _a_numero(fila[columna])
        registros.append(registro)
    return registros


def parsear_carrera(html: str) -> dict[str, dict]:
    """
    Devuelve los agregados de carrera que acb.com publica al final de la
    tabla de temporadas: {'Totales': {...}, 'Promedios': {...}}. A
    diferencia de parsear_temporadas(), estos son los valores REALES de la
    fuente (sumas y promedios de toda la carrera en esa competición), no
    estimaciones nuestras.
    """
    tabla = _tabla_temporadas_normalizada(html)
    if tabla is None:
        return {}

    carrera = {}
    for _, fila in tabla.iterrows():
        etiqueta = str(fila["temporada"]).strip()
        if etiqueta not in ("Totales", "Promedios"):
            continue
        carrera[etiqueta] = {columna: _a_numero(fila[columna]) for columna in COLUMNAS[2:]}
    return carrera


def scrapear_pagina_temporadas(slug_jugador: str, edition_id: int = 90) -> tuple[list[dict], dict[str, dict]]:
    """Descarga la página de temporadas UNA sola vez y devuelve
    (temporadas, carrera) - evita pedirle a acb.com la misma página dos
    veces para obtener ambas cosas."""
    sesion = crear_sesion()
    html = obtener_html(sesion, _url_temporadas(slug_jugador, edition_id))
    if html is None:
        return [], {}
    return parsear_temporadas(html), parsear_carrera(html)


def scrapear_temporadas(slug_jugador: str, edition_id: int = 90) -> list[dict]:
    """Descarga y parsea solo las temporadas (atajo sobre scrapear_pagina_temporadas)."""
    temporadas, _ = scrapear_pagina_temporadas(slug_jugador, edition_id)
    return temporadas


def scrapear_carrera(slug_jugador: str, edition_id: int = 90) -> dict[str, dict]:
    """Descarga y parsea solo la carrera (atajo sobre scrapear_pagina_temporadas)."""
    _, carrera = scrapear_pagina_temporadas(slug_jugador, edition_id)
    return carrera


def guardar_estadisticas(jugador_id: int, registro: dict, competicion: str = "ACB") -> None:
    """
    Inserta o actualiza la fila de estadisticas_temporada de un jugador a
    partir de un registro devuelto por parsear_temporadas()/scrapear_temporadas().
    Crea el equipo si no existe todavía.
    """
    equipo_id = obtener_o_crear_equipo(registro["club"], competicion=competicion)
    partidos = registro.get("partidos_jugados") or 0

    def _total_estimado(promedio: Optional[float]) -> Optional[int]:
        if promedio is None:
            return None
        return round(promedio * partidos)

    def _entero(valor) -> Optional[int]:
        if valor is None:
            return None
        return round(valor)

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
                jugador_id, equipo_id, registro["temporada"], competicion,
                int(partidos) if partidos else None,
                # "5i" también es un promedio por partido (p.ej. 0,9), no un total directo
                _total_estimado(registro.get("cinco_iniciales")),
                _total_estimado(registro.get("minutos_promedio")), registro.get("minutos_promedio"),
                _total_estimado(registro.get("puntos_promedio")), registro.get("puntos_promedio"),
                _entero(registro.get("puntos_max")),
                # Con/Int de tiros son promedios por partido en la tabla de acb.com, no totales
                _total_estimado(registro.get("t2_con")), _total_estimado(registro.get("t2_int")),
                _total_estimado(registro.get("t3_con")), _total_estimado(registro.get("t3_int")),
                _total_estimado(registro.get("tl_con")), _total_estimado(registro.get("tl_int")),
                _total_estimado(registro.get("rebotes_promedio")), registro.get("rebotes_promedio"),
                _total_estimado(registro.get("rebotes_ofe")), _total_estimado(registro.get("rebotes_def")),
                _total_estimado(registro.get("asistencias_promedio")), registro.get("asistencias_promedio"),
                _total_estimado(registro.get("recuperaciones_promedio")),
                _total_estimado(registro.get("tapones_favor")),
                _total_estimado(registro.get("tapones_contra")),
                _total_estimado(registro.get("mates")),
                _total_estimado(registro.get("perdidas_promedio")),
                _total_estimado(registro.get("faltas_cometidas")),
                _total_estimado(registro.get("faltas_recibidas")),
                registro.get("t2_pct"), registro.get("t3_pct"), registro.get("tl_pct"),
                registro.get("mas_menos"), registro.get("valoracion_pir"),
                _entero(registro.get("victorias")), _entero(registro.get("derrotas")),
            ),
        )


def guardar_estadisticas_carrera(jugador_id: int, tipo_fila: str, registro: dict,
                                  competicion: str = "ACB") -> None:
    """
    Inserta o actualiza la fila de estadisticas_carrera (tipo_fila:
    'Totales' o 'Promedios') a partir de un registro de
    parsear_carrera()/scrapear_carrera(). A diferencia de
    guardar_estadisticas(), aquí NO se estima nada: se guardan los valores
    tal cual los publica acb.com (sumas reales en 'Totales', promedio real
    por partido en 'Promedios').
    """
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO estadisticas_carrera
                (jugador_id, competicion, tipo_fila,
                 partidos_jugados, partidos_titular, minutos, puntos, puntos_max,
                 t2_convertidos, t2_intentados, porcentaje_tiro2,
                 t3_convertidos, t3_intentados, porcentaje_tiro3,
                 tl_convertidos, tl_intentados, porcentaje_tiro_libre,
                 rebotes_ofensivos, rebotes_defensivos, rebotes,
                 asistencias, robos, tapones_favor, tapones_contra, mates,
                 perdidas, faltas_cometidas, faltas_recibidas,
                 mas_menos, valoracion_pir, victorias, derrotas, fuente_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    (SELECT id FROM fuentes WHERE nombre = 'Scraping'))
            ON CONFLICT(jugador_id, competicion, tipo_fila)
            DO UPDATE SET
                partidos_jugados = excluded.partidos_jugados,
                partidos_titular = excluded.partidos_titular,
                minutos = excluded.minutos,
                puntos = excluded.puntos,
                puntos_max = excluded.puntos_max,
                t2_convertidos = excluded.t2_convertidos,
                t2_intentados = excluded.t2_intentados,
                porcentaje_tiro2 = excluded.porcentaje_tiro2,
                t3_convertidos = excluded.t3_convertidos,
                t3_intentados = excluded.t3_intentados,
                porcentaje_tiro3 = excluded.porcentaje_tiro3,
                tl_convertidos = excluded.tl_convertidos,
                tl_intentados = excluded.tl_intentados,
                porcentaje_tiro_libre = excluded.porcentaje_tiro_libre,
                rebotes_ofensivos = excluded.rebotes_ofensivos,
                rebotes_defensivos = excluded.rebotes_defensivos,
                rebotes = excluded.rebotes,
                asistencias = excluded.asistencias,
                robos = excluded.robos,
                tapones_favor = excluded.tapones_favor,
                tapones_contra = excluded.tapones_contra,
                mates = excluded.mates,
                perdidas = excluded.perdidas,
                faltas_cometidas = excluded.faltas_cometidas,
                faltas_recibidas = excluded.faltas_recibidas,
                mas_menos = excluded.mas_menos,
                valoracion_pir = excluded.valoracion_pir,
                victorias = excluded.victorias,
                derrotas = excluded.derrotas,
                fuente_id = excluded.fuente_id,
                fecha_actualizacion = datetime('now');
            """,
            (
                jugador_id, competicion, tipo_fila,
                registro.get("partidos_jugados"), registro.get("cinco_iniciales"),
                registro.get("minutos_promedio"), registro.get("puntos_promedio"),
                registro.get("puntos_max"),
                registro.get("t2_con"), registro.get("t2_int"), registro.get("t2_pct"),
                registro.get("t3_con"), registro.get("t3_int"), registro.get("t3_pct"),
                registro.get("tl_con"), registro.get("tl_int"), registro.get("tl_pct"),
                registro.get("rebotes_ofe"), registro.get("rebotes_def"), registro.get("rebotes_promedio"),
                registro.get("asistencias_promedio"),
                registro.get("recuperaciones_promedio"),
                registro.get("tapones_favor"), registro.get("tapones_contra"),
                registro.get("mates"),
                registro.get("perdidas_promedio"),
                registro.get("faltas_cometidas"), registro.get("faltas_recibidas"),
                registro.get("mas_menos"), registro.get("valoracion_pir"),
                registro.get("victorias"), registro.get("derrotas"),
            ),
        )
