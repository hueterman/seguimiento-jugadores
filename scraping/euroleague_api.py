"""
Cliente de la API pública de Euroliga/EuroCup (api-live.euroleague.net).

Confirmado el 2026-10-03 (ver sesión del puente al navegador del usuario +
llamadas directas desde el contenedor):
- Es una API REST real con datos en JSON, SIN necesidad de API key para
  estos endpoints de lectura (a diferencia de lo que sugiere el swagger de
  /v3/, que es para otro namespace distinto y no se usa aquí) - probado con
  llamadas directas que devolvieron datos reales sin cabecera de
  autenticación. A diferencia de acb.com, NO hace falta mirar el HTML: es
  JSON servido directamente.
- GET /v2/competitions/{E|U}/seasons/{E2026|U2026}/clubs
  -> lista de clubes de la competición/temporada, cada uno con 'code',
  'name' y, clave para diferenciar por país, 'country' (p.ej. "Germany",
  "Turkiye", "Spain"...). E = Euroliga, U = EuroCup. El código de temporada
  es la letra de competición + el año de inicio (temporada 2026-2027 de
  Euroliga = "E2026").
- GET /v2/competitions/{E|U}/seasons/{..}/clubs/{clubCode}/people
  -> la plantilla completa de ESE club en ESA temporada: jugadores Y
  cuerpo técnico en la misma llamada (campo 'type': "J"=Jugador,
  "E"=Entrenador, "A"=Entrenador ayudante; también aparecen médicos,
  utilleros, etc. con otros códigos, que se descartan). Cada persona trae
  nombre completo ('person.name', formato "APELLIDOS, Nombre"),
  nacionalidad ('person.country.name'), altura/peso en cm/kg, fecha de
  nacimiento, dorsal, y fechas de alta/baja en el equipo esa temporada.
  OJO: 'person.height'/'weight' vienen a 0 cuando no hay dato (no es un
  valor real) - se tratan como None.
- La posición ('positionName') solo tiene 3 valores en inglés (Guard/
  Forward/Center), mientras que nuestro catálogo 'posiciones' tiene 5 en
  español (Base/Escolta/Alero/Ala-pívot/Pívot) tomados de acb.com. NO hay
  una correspondencia 1:1 fiable (Guard podría ser Base o Escolta, Forward
  podría ser Alero o Ala-pívot) - por eso este módulo NO rellena la
  posición del jugador; se deja tal cual esté (normalmente ya viene de
  ACB si el jugador también juega en esa liga).
- El 'club' que devuelve /people NO trae 'country' (solo code/name/
  tvCode/...) - el país hay que sacarlo de la llamada a /clubs y pasarlo
  aparte (ver obtener_clubes).

Uso de prueba:
    python -m scraping.euroleague_api E E2026 MAD
"""
import argparse
import re

import requests

from scraping.paises import nombre_pais_es

CODIGOS_COMPETICION = {"euroliga": "E", "eurocup": "U"}
NOMBRES_COMPETICION = {"euroliga": "Euroliga", "eurocup": "EuroCup"}

_CABECERAS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

_TIPOS_ENTRENADOR = {"E": "Entrenador", "A": "Entrenador Ayudante"}


def _sesion() -> requests.Session:
    sesion = requests.Session()
    sesion.headers.update(_CABECERAS)
    return sesion


def _url_clubes(codigo_competicion: str, codigo_temporada: str) -> str:
    return f"https://api-live.euroleague.net/v2/competitions/{codigo_competicion}/seasons/{codigo_temporada}/clubs"


def _url_roster(codigo_competicion: str, codigo_temporada: str, codigo_club: str) -> str:
    return (
        f"https://api-live.euroleague.net/v2/competitions/{codigo_competicion}"
        f"/seasons/{codigo_temporada}/clubs/{codigo_club}/people"
    )


def codigo_temporada(codigo_competicion: str, anio: int) -> str:
    """('E', 2026) -> 'E2026'."""
    return f"{codigo_competicion}{anio}"


def temporada_texto(anio: int) -> str:
    """2026 -> '2026-2027' (mismo formato que usa acb.com/nuestra BD)."""
    return f"{anio}-{anio + 1}"


def _separar_nombre(nombre_completo: str) -> tuple[str, str]:
    """'LLULL, SERGIO' -> ('Sergio', 'Llull'). 'SMITH JR, NICK' ->
    ('Nick', 'Smith Jr'). Si no hay coma (no visto en la práctica, pero por
    si acaso), se devuelve todo como nombre y apellidos vacío."""
    partes = nombre_completo.split(",", 1)
    if len(partes) != 2:
        return nombre_completo.strip().title(), ""
    apellidos_raw, nombre_raw = partes
    return nombre_raw.strip().title(), apellidos_raw.strip().title()


def _entero_o_none(valor) -> int | None:
    """Trata 0/None/"" como "sin dato" (altura/peso/dorsal vienen a 0 en
    la API cuando no hay valor real, no es un 0 genuino)."""
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None
    return numero if numero != 0 else None


_PATRON_FECHA = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def _fecha_a_iso(valor: str | None) -> str | None:
    """'2025-11-05T14:46:42.788' -> '2025-11-05'. None si no hay fecha o
    es una fecha "vacía" tipo año 1."""
    if not valor:
        return None
    match = _PATRON_FECHA.match(valor)
    if not match or match.group(1) == "0001":
        return None
    return match.group(0)


def _extraer_nombre_pais(valor) -> str | None:
    """'country' viene como objeto {'code': 'ESP', 'name': 'Spain'}
    (confirmado el 2026-10-03, corrigiendo una suposición anterior basada
    en un resumen y no en el JSON crudo - de ahí este helper, por si en
    algún endpoint viniera como texto plano en vez de objeto). Devuelve el
    nombre en inglés tal cual lo da la API - la traducción a español la
    hace nombre_pais_es() (scraping/paises.py) por separado."""
    if isinstance(valor, dict):
        return valor.get("name")
    return valor


def obtener_clubes(codigo_competicion: str, codigo_temporada_: str) -> dict[str, dict]:
    """Devuelve {codigo_club: {'nombre', 'pais', 'tv_code'}} de todos los
    clubes de esa competición/temporada. 'pais' ya viene traducido a
    español (ver scraping/paises.py - la API lo da en inglés).

    CONFIRMADO el 2026-10-04: cada club trae DOS códigos distintos - 'code'
    (la clave de este diccionario, la misma que usa el resto de esta API,
    p.ej. /clubs/{code}/people) y 'tvCode' (aquí expuesto como 'tv_code'),
    que en muchos clubes es bien distinto ('code' de Fenerbahce es 'ULK',
    su 'tvCode' es 'FNB'; Baskonia es 'BAS'/'KBA'...). 'tv_code' se añade
    como campo informativo, SIN cambiar las claves de este diccionario -
    scraping/actualizar_euroleague.py sigue iterando solo por 'code' (el
    único válido para /people). Quien necesite resolver por 'tv_code' debe
    construirse su propio índice secundario (ver
    scraping/euroleague_estadisticas.py, donde la ficha de estadísticas
    resulta que usa 'tvCode' en vez de 'code')."""
    sesion = _sesion()
    respuesta = sesion.get(_url_clubes(codigo_competicion, codigo_temporada_), timeout=10)
    respuesta.raise_for_status()
    datos = respuesta.json()
    clubes = datos.get("data", datos) if isinstance(datos, dict) else datos
    return {
        club["code"]: {
            "nombre": club["name"],
            "pais": nombre_pais_es(_extraer_nombre_pais(club.get("country"))),
            "tv_code": club.get("tvCode"),
        }
        for club in clubes
    }


def parsear_roster(datos: list[dict]) -> list[dict]:
    """Convierte la respuesta cruda de /people en una lista de diccionarios
    normalizados: {'tipo': 'jugador'|'entrenador', 'nombre', 'apellidos',
    'cargo' (solo entrenadores), 'nacionalidad', 'altura_cm', 'peso_kg',
    'fecha_nacimiento', 'dorsal', 'fecha_inicio', 'fecha_fin', 'id_externo'}.
    Descarta cualquier persona que no sea jugador ni entrenador/entrenador
    ayudante (médicos, utilleros, etc. - no son "cuerpo técnico" tal y como
    lo entendemos en este proyecto)."""
    normalizados = []
    for entrada in datos:
        persona = entrada["person"]
        tipo_codigo = entrada.get("type")
        nombre, apellidos = _separar_nombre(persona["name"])
        activo = bool(entrada.get("active"))
        base = {
            "nombre": nombre,
            "apellidos": apellidos,
            "nacionalidad": nombre_pais_es((persona.get("country") or {}).get("name")),
            "altura_cm": _entero_o_none(persona.get("height")),
            "peso_kg": _entero_o_none(persona.get("weight")),
            "fecha_nacimiento": _fecha_a_iso(persona.get("birthDate")),
            "dorsal": _entero_o_none(entrada.get("dorsal")),
            "fecha_inicio": _fecha_a_iso(entrada.get("startDate")),
            "fecha_fin": None if activo else _fecha_a_iso(entrada.get("endDate")),
            "id_externo": persona.get("code"),
        }
        if tipo_codigo == "J":
            normalizados.append({**base, "tipo": "jugador"})
        elif tipo_codigo in _TIPOS_ENTRENADOR:
            normalizados.append({**base, "tipo": "entrenador", "cargo": _TIPOS_ENTRENADOR[tipo_codigo]})
        # cualquier otro 'type' (médico, utillero, delegado...) se descarta
    return normalizados


def obtener_roster_club(codigo_competicion: str, codigo_temporada_: str, codigo_club: str) -> list[dict]:
    """Descarga y normaliza la plantilla (jugadores + cuerpo técnico) de un
    club en una competición/temporada (ver parsear_roster)."""
    sesion = _sesion()
    respuesta = sesion.get(
        _url_roster(codigo_competicion, codigo_temporada_, codigo_club), timeout=10,
    )
    respuesta.raise_for_status()
    datos = respuesta.json()
    datos = datos.get("data", datos) if isinstance(datos, dict) else datos
    return parsear_roster(datos)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prueba puntual contra la API de Euroliga/EuroCup.")
    parser.add_argument("codigo_competicion", choices=["E", "U"])
    parser.add_argument("codigo_temporada")
    parser.add_argument("codigo_club")
    args = parser.parse_args()
    for persona in obtener_roster_club(args.codigo_competicion, args.codigo_temporada, args.codigo_club):
        print(persona)
