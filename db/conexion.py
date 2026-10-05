"""
Utilidades de conexión y acceso a catálogos/equipos, compartidas por el
scraper y por la interfaz de formularios manuales.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import DB_PATH

CATALOGOS_VALIDOS = {
    "posiciones", "tipos_movimiento", "manos_dominantes", "estados_jugador",
    "fuentes", "niveles_fiabilidad", "grados_gravedad", "estados_lesion",
    "tipos_contrato",
}


@contextmanager
def get_connection():
    """Context manager que abre una conexión con claves foráneas activadas."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _validar_catalogo(nombre_tabla: str) -> None:
    if nombre_tabla not in CATALOGOS_VALIDOS:
        raise ValueError(f"'{nombre_tabla}' no es un catálogo reconocido.")


def listar_catalogo(nombre_tabla: str) -> list[sqlite3.Row]:
    """Devuelve todas las filas (id, nombre) de una tabla de catálogo."""
    _validar_catalogo(nombre_tabla)
    with get_connection() as conn:
        cursor = conn.execute(f"SELECT id, nombre FROM {nombre_tabla} ORDER BY id;")
        return cursor.fetchall()


def id_por_nombre(nombre_tabla: str, nombre_valor: str) -> int | None:
    """Busca el id de un valor de catálogo por su nombre (ej. 'Activo' en estados_jugador)."""
    _validar_catalogo(nombre_tabla)
    with get_connection() as conn:
        cursor = conn.execute(
            f"SELECT id FROM {nombre_tabla} WHERE nombre = ?;", (nombre_valor,)
        )
        row = cursor.fetchone()
        return row["id"] if row else None


def buscar_o_crear_jugador(nombre: str, apellidos: str) -> tuple[int, bool]:
    """Devuelve (jugador_id, creado). Busca por nombre+apellidos, SIN
    distinguir mayúsculas/minúsculas (COLLATE NOCASE) para que no se
    dupliquen jugadores por pequeñas diferencias de capitalización entre
    un alta manual y un alta automática (ej. 'Verge-jr' vs 'Verge-Jr'); si
    hay más de uno con el mismo nombre, avisa y usa el primero (edítalo a
    mano después si hace falta distinguirlos). Compartida por
    scraping/alta_masiva.py y scraping/actualizar_equipo.py para no
    duplicar la misma lógica de alta."""
    with get_connection() as conn:
        coincidencias = conn.execute(
            "SELECT id FROM jugadores WHERE nombre = ? COLLATE NOCASE AND apellidos = ? COLLATE NOCASE;",
            (nombre, apellidos),
        ).fetchall()
        if coincidencias:
            if len(coincidencias) > 1:
                print(
                    f"  [aviso] hay {len(coincidencias)} jugadores llamados "
                    f"'{nombre} {apellidos}' - usando el primero (id={coincidencias[0]['id']})."
                )
            return coincidencias[0]["id"], False

        cursor = conn.execute(
            "INSERT INTO jugadores (nombre, apellidos) VALUES (?, ?);",
            (nombre, apellidos),
        )
        return cursor.lastrowid, True


def actualizar_posicion_jugador(jugador_id: int, posicion_nombre: str | None) -> None:
    """Actualiza posicion_id de un jugador a partir del nombre de la
    posición (debe existir en el catálogo 'posiciones'); no hace nada si
    viene vacía o no se reconoce. Pensada para scraping/actualizar_equipo.py,
    que sí conoce la posición de cada jugador (la propia plantilla la
    publica) a diferencia del alta manual."""
    if not posicion_nombre:
        return
    posicion_id = id_por_nombre("posiciones", posicion_nombre)
    if posicion_id is None:
        print(f"  [aviso] posición '{posicion_nombre}' no está en el catálogo 'posiciones' - se ignora.")
        return
    with get_connection() as conn:
        conn.execute(
            "UPDATE jugadores SET posicion_id = ?, fecha_actualizacion = datetime('now') WHERE id = ?;",
            (posicion_id, jugador_id),
        )


def actualizar_datos_personales_jugador(
    jugador_id: int,
    altura_cm: int | None = None,
    peso_kg: int | None = None,
    fecha_nacimiento: str | None = None,
    nacionalidad: str | None = None,
    id_externo_euroleague: str | None = None,
    foto_url: str | None = None,
) -> None:
    """Actualiza datos personales de un jugador con lo que venga de
    scraping/ficha_jugador.py (ACB) o scraping/euroleague_api.py
    (Euroliga/EuroCup). Solo toca las columnas cuyo valor viene informado
    (no None) - si una pasada concreta no trae un dato puntual, no borra lo
    que ya hubiera en la BD (manual o de una fuente anterior). peso_kg e
    id_externo_euroleague vienen siempre en None desde el flujo de ACB (esa
    fuente no publica ninguno de los dos). foto_url llega de scraping/
    ficha_jugador.py (ACB) o de scraping/euroleague_foto.py (Euroliga/
    EuroCup, desde la plantilla web - la API api-live.euroleague.net NO
    publica fotos, comprobado el 2026-10-04: 'person.images' viene siempre
    vacío)."""
    campos = []
    valores: list = []
    if altura_cm is not None:
        campos.append("altura_cm = ?")
        valores.append(altura_cm)
    if peso_kg is not None:
        campos.append("peso_kg = ?")
        valores.append(peso_kg)
    if fecha_nacimiento is not None:
        campos.append("fecha_nacimiento = ?")
        valores.append(fecha_nacimiento)
    if nacionalidad is not None:
        campos.append("nacionalidad = ?")
        valores.append(nacionalidad)
    if id_externo_euroleague is not None:
        campos.append("id_externo_euroleague = ?")
        valores.append(id_externo_euroleague)
    if foto_url is not None:
        campos.append("foto_url = ?")
        valores.append(foto_url)
    if not campos:
        return
    campos.append("fecha_actualizacion = datetime('now')")
    valores.append(jugador_id)
    with get_connection() as conn:
        conn.execute(f"UPDATE jugadores SET {', '.join(campos)} WHERE id = ?;", valores)


def obtener_o_crear_equipo(nombre: str, competicion: str | None = None,
                            nivel: str | None = None, pais: str | None = None) -> int:
    """Busca un equipo por nombre (y competición si se indica); si no existe,
    lo crea. Si ya existe pero no tenía país guardado y ahora se informa uno
    (p.ej. la API de Euroliga sí lo da; el scraper de ACB hasta ahora no lo
    rellenaba), lo completa - sin pisar un país ya guardado."""
    with get_connection() as conn:
        if competicion:
            fila = conn.execute(
                "SELECT id, pais FROM equipos WHERE nombre = ? AND competicion = ?;",
                (nombre, competicion),
            ).fetchone()
        else:
            fila = conn.execute(
                "SELECT id, pais FROM equipos WHERE nombre = ?;", (nombre,)
            ).fetchone()
        if fila:
            if pais and not fila["pais"]:
                conn.execute("UPDATE equipos SET pais = ? WHERE id = ?;", (pais, fila["id"]))
            return fila["id"]

        cursor = conn.execute(
            "INSERT INTO equipos (nombre, competicion, nivel, pais) VALUES (?, ?, ?, ?);",
            (nombre, competicion, nivel, pais),
        )
        return cursor.lastrowid
