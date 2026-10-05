"""
Diagnóstico de posibles duplicados de jugadores tras combinar ACB con
Euroliga/EuroCup. Dos tipos de problema a buscar:

1. Duplicados EXACTOS (mismo nombre+apellidos, ignorando mayúsculas): no
   deberían existir si todo pasó por db.conexion.buscar_o_crear_jugador,
   pero pueden quedar restos de altas manuales anteriores a esa lógica.

2. Posibles NO-fusiones: dos filas que deberían ser la misma persona pero
   quedaron separadas porque el nombre no coincidía ni ignorando
   mayúsculas - el caso más probable son las tildes (buscar_o_crear_jugador
   usa COLLATE NOCASE, que en SQLite solo pliega A-Z/a-z, NO quita tildes:
   "Álvaro" y "Alvaro" son dos cadenas distintas para esa comparación).
   Aquí se agrupan los nombres quitando tildes y espacios extra para
   encontrar esos casos.

No se puede detectar de forma automática la fusión INCORRECTA (dos
personas reales distintas con el mismo nombre fusionadas en una) sin más
información - para eso se lista quién tiene id de las dos fuentes a la vez,
para revisar a ojo si algo no encaja (nacionalidad/fecha de nacimiento
incoherente con el equipo, etc.).

Uso:
    python -m scraping.diagnosticar_duplicados
"""
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from db.conexion import get_connection


def _normalizar(texto: str | None) -> str:
    """Quita tildes, pasa a minúsculas y colapsa espacios."""
    if not texto:
        return ""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return " ".join(sin_tildes.lower().split())


def duplicados_exactos() -> list:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT nombre, apellidos, COUNT(*) AS n, GROUP_CONCAT(id) AS ids
            FROM jugadores
            GROUP BY nombre COLLATE NOCASE, apellidos COLLATE NOCASE
            HAVING COUNT(*) > 1;
            """
        ).fetchall()


def posibles_no_fusionados() -> list[list]:
    with get_connection() as conn:
        filas = conn.execute(
            "SELECT id, nombre, apellidos, id_externo_acb, id_externo_euroleague, "
            "fecha_nacimiento FROM jugadores;"
        ).fetchall()

    grupos = defaultdict(list)
    for fila in filas:
        clave = (_normalizar(fila["nombre"]), _normalizar(fila["apellidos"]))
        grupos[clave].append(fila)

    return [
        grupo for grupo in grupos.values()
        if len({(f["nombre"], f["apellidos"]) for f in grupo}) > 1
    ]


def jugadores_duales() -> list:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT nombre, apellidos, fecha_nacimiento, nacionalidad,
                   id_externo_acb, id_externo_euroleague
            FROM jugadores
            WHERE id_externo_acb IS NOT NULL AND id_externo_euroleague IS NOT NULL
            ORDER BY apellidos COLLATE NOCASE;
            """
        ).fetchall()


if __name__ == "__main__":
    print("=== 1) Duplicados EXACTOS (mismo nombre+apellidos) ===")
    exactos = duplicados_exactos()
    if not exactos:
        print("Ninguno.")
    for fila in exactos:
        print(f"  {fila['nombre']} {fila['apellidos']}: {fila['n']} filas (ids {fila['ids']})")

    print("\n=== 2) Posibles NO-fusiones (misma persona probable, grafía distinta) ===")
    sospechosos = posibles_no_fusionados()
    if not sospechosos:
        print("Ninguno.")
    for grupo in sospechosos:
        print("  Grupo:")
        for f in grupo:
            print(f"    id={f['id']}: '{f['nombre']} {f['apellidos']}' "
                  f"(acb={f['id_externo_acb']}, euroleague={f['id_externo_euroleague']}, "
                  f"nacimiento={f['fecha_nacimiento']})")

    print("\n=== 3) Jugadores fusionados ACB + Euroliga/EuroCup (revisar a ojo) ===")
    duales = jugadores_duales()
    print(f"{len(duales)} jugador(es) con ambos orígenes:\n")
    for f in duales:
        print(f"  {f['nombre']} {f['apellidos']} - nacimiento={f['fecha_nacimiento']}, "
              f"nacionalidad={f['nacionalidad']}")
