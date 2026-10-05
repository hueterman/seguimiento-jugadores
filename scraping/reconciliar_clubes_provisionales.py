"""
Reconciliación de los equipos "provisionales" de Euroliga/EuroCup.

Por qué existe: scraping/euroleague_estadisticas.py, cuando no puede
resolver el código de 3-4 letras de un club contra la API de clubes para
esa temporada exacta (ver su docstring), guarda la fila de todos modos
usando el código como nombre de equipo provisional (equipos.pais = NULL) -
decisión explícita del usuario para no perder nunca estadísticas (ver
conversación del 2026-10-03/04). Con el backfill completo ya hecho
(687/795 jugadores, 0 errores), toca limpiar esos nombres provisionales.

Qué hace, por cada equipo con pais NULL en competicion Euroliga/EuroCup:
  - Busca si YA existe un equipo real para esa misma competición cuyo
    nombre reconocido contiene la "clave de búsqueda" del código (ej. el
    código "PAO" -> clave "Panathinaikos" -> encuentra el equipo ya
    resuelto "Panathinaikos AKTOR Athens"). Si encuentra EXACTAMENTE uno,
    FUSIONA: reasigna todas las referencias (estadisticas_temporada,
    entrenadores, trayectoria x2, datos_economicos) a ese equipo real y
    borra la fila provisional.
  - Si no encuentra ninguno, o encuentra más de uno (clubes con varias
    variantes de nombre por patrocinador en distintas temporadas, ej.
    "Partizan" tiene 6 filas distintas ya resueltas - no se puede saber a
    cuál corresponde sin mirar la temporada exacta), NO fusiona - solo
    renombra la fila provisional con un nombre y país genéricos
    razonables, para no arriesgar mezclar la fila con la temporada
    equivocada de patrocinador.
  - Si dos códigos distintos (ej. "VBC" y "VIR", ambos Virtus Bologna)
    acaban queriendo el mismo nombre genérico, el segundo que se procese
    chocará con el UNIQUE(nombre, competicion) al renombrar - se detecta
    y se fusiona automáticamente con el primero en vez de fallar.

MAPEO_CODIGOS: diccionario editable con los códigos ya identificados con
confianza razonable a partir del log del backfill (basado en conocimiento
del dominio, no en una fuente verificada automáticamente - revisa si ves
algo raro). Los códigos NO incluidos se dejan tal cual - el informe
(--dry-run, modo por defecto) los lista ordenados por frecuencia de uso
para ir añadiéndolos a mano cuando se identifiquen con seguridad.

ACTUALIZACIÓN 2026-10-04: además de MAPEO_CODIGOS, este script hace
primero una pasada de "resolución paralela" (ver
reconciliar_resolucion_paralela): para cada fila de un equipo
provisional, comprueba si ESE MISMO jugador/temporada/competicion YA
tiene otra fila bajo un equipo real. Esto pasa automáticamente ahora que
scraping/euroleague_estadisticas.py arregló dos bugs de raíz (buscaba el
club por 'code' en vez de 'tvCode', y con la competición de la URL en
vez de la del propio código de temporada) - el backfill de hoy resolvió
TODAS las fichas sin un solo aviso de club no encontrado, pero las filas
VIEJAS de pasadas anteriores siguen bajo el equipo provisional hasta que
se reasignan. A diferencia de MAPEO_CODIGOS (que asigna un nombre fijo a
TODO un código, sin importar la temporada), esta pasada nunca adivina:
solo actúa fila a fila, cuando hay una resolución paralela EXACTA para
ese jugador y esa temporada - así es inmune a que un mismo código de 3
letras se haya reutilizado por dos clubes distintos en épocas distintas
(visto en el informe del 2026-10-04: BKN, KBA, LIE, AXM, JLB, FNB, FBU...
solo casaban para PARTE de sus filas - probablemente esas otras
temporadas de verdad no están todavía en la API de clubes). Gracias a
esto, MAPEO_CODIGOS ya no necesita ampliarse a mano para la inmensa
mayoría de los códigos que antes salían "sin mapeo".

Deliberadamente fuera de alcance: los equipos de competicion='ACB' con
pais NULL (son nombres completos de patrocinador histórico sin país
rellenado, un problema distinto y preexistente - no códigos de 3 letras).

IMPORTANTE: ejecutar esto en tu PROPIO PowerShell, NUNCA a través de
Claude - escribe en la base de datos en vivo (ver
scraping/actualizar_estadisticas_euroleague.py, mismo motivo).

Uso:
    python -m scraping.reconciliar_clubes_provisionales            # informe, no cambia nada
    python -m scraping.reconciliar_clubes_provisionales --aplicar  # aplica los cambios
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from db.conexion import get_connection

# Las dos competiciones donde scraping/euroleague_estadisticas.py guarda
# equipos provisionales (mismos valores literales que usa ese módulo).
_COMPETICIONES = ("Euroliga", "EuroCup")

# código tal como aparece en la ficha de estadísticas -> (nombre genérico
# a usar si no se fusiona con nada, país en español tal como lo usa
# scraping/paises.py, fragmento de búsqueda para localizar un equipo YA
# resuelto con ese nombre real en esa misma competición).
MAPEO_CODIGOS: dict[str, tuple[str, str, str]] = {
    # Grecia
    "PAO": ("Panathinaikos", "Grecia", "Panathinaikos"),
    "PAN": ("Panathinaikos", "Grecia", "Panathinaikos"),
    "OLY": ("Olympiacos Piraeus", "Grecia", "Olympiacos"),
    "ARI": ("Aris Thessaloniki", "Grecia", "Aris"),
    "AEK": ("AEK Athens", "Grecia", "AEK"),
    # Turquía
    "EFS": ("Anadolu Efes Istanbul", "Turquía", "Anadolu Efes"),
    "FBB": ("Fenerbahce Istanbul", "Turquía", "Fenerbahce"),
    "BJK": ("Besiktas Istanbul", "Turquía", "Besiktas"),
    "TOF": ("Tofas Bursa", "Turquía", "Tofas"),
    # España
    "RMB": ("Real Madrid", "España", "Real Madrid"),
    "RMA": ("Real Madrid", "España", "Real Madrid"),
    "FCB": ("FC Barcelona", "España", "Barcelona"),
    "MAN": ("Manresa", "España", "Manresa"),
    "BUR": ("San Pablo Burgos", "España", "Burgos"),
    # Israel
    "MTA": ("Maccabi Tel Aviv", "Israel", "Maccabi"),
    "JLM": ("Hapoel Jerusalem", "Israel", "Jerusalem"),
    # Serbia / Bosnia / Montenegro
    "CZV": ("Crvena Zvezda Belgrade", "Serbia", "Crvena Zvezda"),
    "CZT": ("Crvena Zvezda Belgrade", "Serbia", "Crvena Zvezda"),
    "PAR": ("Partizan Belgrade", "Serbia", "Partizan"),
    "BOS": ("Bosna Sarajevo", "Bosnia y Herzegovina", "BOSNA"),
    "BUD": ("Buducnost VOLI Podgorica", "Montenegro", "Buducnost"),
    # Italia
    "VBC": ("Virtus Bologna", "Italia", "Virtus"),
    "VIR": ("Virtus Bologna", "Italia", "Virtus"),
    "EA7": ("Olimpia Milano", "Italia", "Milan"),
    "MIL": ("Olimpia Milano", "Italia", "Milan"),
    "TRE": ("Trento", "Italia", "Trento"),
    "DER": ("Derthona Tortona", "Italia", "Derthona"),
    "ROM": ("Roma Basketball", "Italia", "Roma"),
    "NAP": ("Napoli Basketball", "Italia", "Napoli"),
    "REG": ("Reggio Emilia", "Italia", "Reggio"),
    # Alemania
    "BAY": ("Bayern Munich", "Alemania", "Bayern"),
    "BRO": ("Brose Bamberg", "Alemania", "Brose"),
    "HAM": ("Hamburg Towers", "Alemania", "Hamburg"),
    "ROS": ("Rostock Seawolves", "Alemania", "Rostock"),
    "SKY": ("Skyliners Frankfurt", "Alemania", "Skyliners"),
    "NIN": ("NINERS Chemnitz", "Alemania", "NINERS"),
    "ULM": ("ratiopharm Ulm", "Alemania", "Ulm"),
    "ALB": ("ALBA Berlin", "Alemania", "ALBA Berlin"),
    "BER": ("ALBA Berlin", "Alemania", "ALBA Berlin"),
    # Francia
    "ASM": ("AS Monaco", "Mónaco", "Monaco"),
    "ASV": ("LDLC ASVEL Villeurbanne", "Francia", "ASVEL"),
    "PBB": ("Paris Basketball", "Francia", "Paris Basketball"),
    "SIG": ("Strasbourg SIG", "Francia", "Strasbourg"),
    # Lituania / Letonia / Polonia
    "ZAL": ("Zalgiris Kaunas", "Lituania", "Zalgiris"),
    "LRY": ("Lietuvos Rytas Vilnius", "Lituania", "Lietuvos Rytas"),
    "RYT": ("Lietuvos Rytas Vilnius", "Lituania", "Lietuvos Rytas"),
    "NEP": ("Neptunas Klaipeda", "Lituania", "Neptunas"),
    "SIA": ("Siauliai Basketball", "Lituania", "Siauliai"),
    "WLV": ("Wolves Vilnius", "Lituania", "Wolves"),
    "VEF": ("VEF Riga", "Letonia", "VEF Riga"),
    "RIG": ("Riga", "Letonia", "Riga"),
    "WKS": ("Slask Wroclaw", "Polonia", "Slask"),
    # Rusia
    "CSK": ("CSKA Moscow", "Rusia", "CSKA"),
    "KHI": ("Khimki Moscow Region", "Rusia", "Khimki"),
    # Rumanía / Reino Unido / Emiratos
    "UBT": ("U-BT Cluj-Napoca", "Rumanía", "U-BT"),
    "LDN": ("London Lions", "Reino Unido", "London"),
    "DUB": ("Dubai Basketball", "Emiratos Árabes Unidos", "Dubai"),
}


def _provisionales(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Equipos de Euroliga/EuroCup con pais NULL (candidatos a
    provisionales), con su frecuencia de uso real (filas de
    estadisticas_temporada ya guardadas con ese equipo)."""
    marcadores = ",".join("?" * len(_COMPETICIONES))
    return conn.execute(
        f"""
        SELECT e.id, e.nombre, e.competicion, COUNT(et.id) AS n_filas
        FROM equipos e
        LEFT JOIN estadisticas_temporada et ON et.equipo_id = e.id
        WHERE e.competicion IN ({marcadores}) AND e.pais IS NULL
        GROUP BY e.id
        ORDER BY n_filas DESC;
        """,
        _COMPETICIONES,
    ).fetchall()


def _candidatos_reales(conn: sqlite3.Connection, competicion: str, clave_busqueda: str,
                        excluir_id: int) -> list[sqlite3.Row]:
    """Equipos YA resueltos (pais no nulo) de esa competición cuyo nombre
    contiene la clave de búsqueda EMPEZANDO en un límite de palabra (se
    exige un espacio - o el propio inicio del nombre, vía el espacio que
    se añade delante - justo antes de la clave). Sin esto, "Aris" encajaba
    por subcadena dentro de "Paris Basketball" y "Wolves" dentro de
    "Rostock Seawolves" - confirmado y corregido el 2026-10-04. El lado
    derecho SÍ queda abierto a propósito (ej. la clave "Milan" debe seguir
    encajando con "Armani Jeans Milano")."""
    return conn.execute(
        "SELECT id, nombre FROM equipos "
        "WHERE competicion = ? AND pais IS NOT NULL AND id != ? "
        "AND (' ' || nombre) LIKE ?;",
        (competicion, excluir_id, f"% {clave_busqueda}%"),
    ).fetchall()


# Columnas de estadisticas_temporada que NO cuentan como "dato real" al
# comparar qué fila duplicada es más completa (ver _reasignar_estadisticas_temporada).
_COLUMNAS_META_ESTADISTICAS = {
    "id", "jugador_id", "equipo_id", "temporada", "competicion", "fuente_id", "fecha_actualizacion",
}


def _completitud(fila: sqlite3.Row) -> int:
    """Nº de columnas de datos (no id/jugador/equipo/temporada/competicion/
    metadatos) con algún valor - para decidir, entre dos filas duplicadas
    del mismo jugador+temporada, cuál conservar."""
    return sum(1 for clave in fila.keys() if clave not in _COLUMNAS_META_ESTADISTICAS and fila[clave] is not None)


def _reasignar_estadisticas_temporada(conn: sqlite3.Connection, origen_id: int, destino_id: int) -> None:
    """Mueve al equipo destino las filas de estadisticas_temporada del
    equipo origen. Si el jugador YA tenía una fila para ese mismo
    (destino, temporada, competicion) - el mismo jugador/temporada
    guardado dos veces bajo dos equipo_id distintos, visto el 2026-10-04
    al fusionar 'OLY' con Olympiacos Piraeus (violaba el UNIQUE de esa
    tabla) - se queda la más completa de las dos (más columnas con dato) y
    se borra la otra; nunca se pierden ambas, y se avisa por print para
    poder auditarlo."""
    duplicadas = conn.execute(
        "SELECT * FROM estadisticas_temporada WHERE equipo_id = ?;", (origen_id,)
    ).fetchall()
    for fila in duplicadas:
        conflicto = conn.execute(
            "SELECT * FROM estadisticas_temporada "
            "WHERE jugador_id = ? AND equipo_id = ? AND temporada = ? AND competicion = ?;",
            (fila["jugador_id"], destino_id, fila["temporada"], fila["competicion"]),
        ).fetchone()
        if conflicto is None:
            conn.execute(
                "UPDATE estadisticas_temporada SET equipo_id = ? WHERE id = ?;",
                (destino_id, fila["id"]),
            )
            continue
        # Duplicado real: dos filas para el mismo jugador+temporada+competicion,
        # una ya contra el equipo destino y otra contra el provisional.
        ganadora, perdedora = (fila, conflicto) if _completitud(fila) > _completitud(conflicto) else (conflicto, fila)
        conn.execute("DELETE FROM estadisticas_temporada WHERE id = ?;", (perdedora["id"],))
        if ganadora["id"] == fila["id"]:
            conn.execute(
                "UPDATE estadisticas_temporada SET equipo_id = ? WHERE id = ?;",
                (destino_id, ganadora["id"]),
            )
        print(
            f"    [aviso] jugador_id={fila['jugador_id']} temporada={fila['temporada']} - "
            f"había 2 filas duplicadas (una ya en el equipo destino) - se queda la más completa "
            f"(id={ganadora['id']}), se borra id={perdedora['id']}"
        )


def _actualizar_fila_a_fila(conn: sqlite3.Connection, tabla: str, columna: str,
                             origen_id: int, destino_id: int) -> int:
    """Reasigna fila a fila (no en bloque) para no abortar si alguna fila
    choca con una restricción UNIQUE propia de esa tabla que no se ha
    modelado aquí. Devuelve cuántas filas quedaron SIN reasignar (siguen
    apuntando al equipo origen)."""
    filas = conn.execute(f"SELECT id FROM {tabla} WHERE {columna} = ?;", (origen_id,)).fetchall()
    pendientes = 0
    for fila in filas:
        try:
            conn.execute(f"UPDATE {tabla} SET {columna} = ? WHERE id = ?;", (destino_id, fila["id"]))
        except sqlite3.IntegrityError as error:
            pendientes += 1
            print(f"    [aviso] no se pudo reasignar {tabla}.id={fila['id']} ({columna}): {error}")
    return pendientes


def _reasignar_y_borrar(conn: sqlite3.Connection, origen_id: int, destino_id: int) -> bool:
    """Mueve todo lo que apunta al equipo 'origen_id' hacia 'destino_id' y
    borra la fila provisional si queda sin referencias. Devuelve False (y
    NO borra la fila provisional) si algo se quedó sin poder reasignar -
    mejor dejar el equipo provisional vivo que perder la referencia."""
    _reasignar_estadisticas_temporada(conn, origen_id, destino_id)
    pendientes = 0
    for tabla, columna in (
        ("entrenadores", "equipo_id"),
        ("trayectoria", "equipo_id"),
        ("trayectoria", "equipo_procedencia_id"),
        ("datos_economicos", "equipo_id"),
    ):
        pendientes += _actualizar_fila_a_fila(conn, tabla, columna, origen_id, destino_id)

    quedan = conn.execute(
        "SELECT COUNT(*) AS n FROM estadisticas_temporada WHERE equipo_id = ?;", (origen_id,)
    ).fetchone()["n"]
    if pendientes or quedan:
        print(f"    [aviso] el equipo provisional id={origen_id} NO se borra - aún tiene referencias sin reasignar.")
        return False
    conn.execute("DELETE FROM equipos WHERE id = ?;", (origen_id,))
    return True


def _resolucion_paralela(conn: sqlite3.Connection, jugador_id: int, temporada: str,
                          competicion: str, excluir_equipo_id: int) -> int | None:
    """Busca si ESTE jugador/temporada/competicion ya tiene otra fila bajo
    un equipo YA resuelto (pais no nulo) - la reasignación que hace el
    propio backfill (con los dos fixes de raíz del 2026-10-04) para esa
    misma fila, bajo un equipo_id distinto al provisional. Devuelve ese
    equipo_id, o None si no hay ninguno (de verdad no está resuelta
    todavía esa temporada)."""
    fila = conn.execute(
        "SELECT et.equipo_id FROM estadisticas_temporada et "
        "JOIN equipos e ON e.id = et.equipo_id "
        "WHERE et.jugador_id = ? AND et.temporada = ? AND et.competicion = ? "
        "AND e.pais IS NOT NULL AND et.equipo_id != ? LIMIT 1;",
        (jugador_id, temporada, competicion, excluir_equipo_id),
    ).fetchone()
    return fila["equipo_id"] if fila else None


def _reasignar_una_fila(conn: sqlite3.Connection, fila_id: int, destino_id: int) -> None:
    """Como _reasignar_estadisticas_temporada, pero para UNA sola fila
    (usado por la resolución paralela, donde cada fila de un mismo equipo
    provisional puede ir a un destino distinto según la temporada) - mismo
    manejo de duplicados por completitud si el jugador ya tenía una fila
    en el destino."""
    fila = conn.execute("SELECT * FROM estadisticas_temporada WHERE id = ?;", (fila_id,)).fetchone()
    conflicto = conn.execute(
        "SELECT * FROM estadisticas_temporada "
        "WHERE jugador_id = ? AND equipo_id = ? AND temporada = ? AND competicion = ? AND id != ?;",
        (fila["jugador_id"], destino_id, fila["temporada"], fila["competicion"], fila_id),
    ).fetchone()
    if conflicto is None:
        conn.execute("UPDATE estadisticas_temporada SET equipo_id = ? WHERE id = ?;", (destino_id, fila_id))
        return
    ganadora, perdedora = (fila, conflicto) if _completitud(fila) > _completitud(conflicto) else (conflicto, fila)
    conn.execute("DELETE FROM estadisticas_temporada WHERE id = ?;", (perdedora["id"],))
    if ganadora["id"] == fila["id"]:
        conn.execute("UPDATE estadisticas_temporada SET equipo_id = ? WHERE id = ?;", (destino_id, ganadora["id"]))
    print(
        f"    [aviso] jugador_id={fila['jugador_id']} temporada={fila['temporada']} - "
        f"había 2 filas duplicadas (una ya en el equipo destino) - se queda la más completa "
        f"(id={ganadora['id']}), se borra id={perdedora['id']}"
    )


def reconciliar_resolucion_paralela(conn: sqlite3.Connection, aplicar: bool) -> None:
    """Primera pasada (ver docstring del módulo): reasigna fila a fila
    cualquier estadística de un equipo provisional cuyo jugador/temporada/
    competicion YA tenga otra fila bajo un equipo real. Borra el equipo
    provisional si se queda sin ninguna referencia en ninguna tabla."""
    marcadores = ",".join("?" * len(_COMPETICIONES))
    provisionales = conn.execute(
        f"SELECT id, nombre, competicion FROM equipos WHERE competicion IN ({marcadores}) AND pais IS NULL;",
        _COMPETICIONES,
    ).fetchall()

    total_reasignadas = 0
    total_sin_resolver = 0
    equipos_vaciados = 0

    for prov in provisionales:
        if aplicar:
            conn.execute("SAVEPOINT paralelo;")
        try:
            filas = conn.execute(
                "SELECT id, jugador_id, temporada FROM estadisticas_temporada WHERE equipo_id = ?;",
                (prov["id"],),
            ).fetchall()
            reasignadas_aqui = 0
            for fila in filas:
                destino = _resolucion_paralela(conn, fila["jugador_id"], fila["temporada"],
                                                 prov["competicion"], prov["id"])
                if destino is None:
                    total_sin_resolver += 1
                    continue
                reasignadas_aqui += 1
                if aplicar:
                    _reasignar_una_fila(conn, fila["id"], destino)
            total_reasignadas += reasignadas_aqui

            if aplicar and reasignadas_aqui:
                quedan = conn.execute(
                    "SELECT COUNT(*) AS n FROM estadisticas_temporada WHERE equipo_id = ?;", (prov["id"],)
                ).fetchone()["n"]
                otras = sum(
                    conn.execute(
                        f"SELECT COUNT(*) AS n FROM {tabla} WHERE {columna} = ?;", (prov["id"],)
                    ).fetchone()["n"]
                    for tabla, columna in (
                        ("entrenadores", "equipo_id"), ("trayectoria", "equipo_id"),
                        ("trayectoria", "equipo_procedencia_id"), ("datos_economicos", "equipo_id"),
                    )
                )
                if quedan == 0 and otras == 0:
                    conn.execute("DELETE FROM equipos WHERE id = ?;", (prov["id"],))
                    equipos_vaciados += 1
        except Exception as error:
            if aplicar:
                conn.execute("ROLLBACK TO paralelo;")
            print(f"  [error] equipo provisional '{prov['nombre']}' ({prov['competicion']}) "
                  f"id={prov['id']} - no se pudo procesar: {error}")
            continue
        finally:
            if aplicar:
                conn.execute("RELEASE paralelo;")

    print(
        f"Resolución paralela: {total_reasignadas} fila(s) "
        f"{'reasignadas' if aplicar else 'reasignables'} a su equipo real ya resuelto, "
        f"{equipos_vaciados} equipo(s) provisional(es) vaciados y borrados, "
        f"{total_sin_resolver} fila(s) sin resolución paralela todavía "
        f"({'APLICADO' if aplicar else 'sin aplicar - repite con --aplicar'})."
    )


def reconciliar(aplicar: bool) -> None:
    with get_connection() as conn:
        reconciliar_resolucion_paralela(conn, aplicar)
        print()

        filas = _provisionales(conn)
        sin_mapeo = []
        n_fusionados = 0
        n_renombrados = 0

        for fila in filas:
            codigo = fila["nombre"]
            mapeo = MAPEO_CODIGOS.get(codigo)
            if mapeo is None:
                sin_mapeo.append(fila)
                continue

            nombre_generico, pais, clave = mapeo
            candidatos = _candidatos_reales(conn, fila["competicion"], clave, fila["id"])

            # Cada código se procesa en su propio SAVEPOINT: si algo falla de
            # forma inesperada (una restricción que no se había previsto, ej.
            # el UNIQUE de estadisticas_temporada visto el 2026-10-04 al
            # fusionar 'OLY'), se deshace SOLO ese código y se sigue con el
            # resto - nunca se pierde lo que ya se había conseguido antes.
            if aplicar:
                conn.execute("SAVEPOINT codigo;")
            try:
                if len(candidatos) == 1:
                    destino = candidatos[0]
                    print(f"  {codigo:<6} ({fila['competicion']:<8} {fila['n_filas']:>3} filas) "
                          f"-> FUSIONAR con '{destino['nombre']}' (id={destino['id']})")
                    if aplicar:
                        _reasignar_y_borrar(conn, fila["id"], destino["id"])
                    n_fusionados += 1
                else:
                    nota = ""
                    if candidatos:
                        nota = (f"  [ambiguo: {len(candidatos)} equipos ya resueltos coinciden con "
                                f"'{clave}' - no se fusiona para no mezclar temporadas de patrocinador distintas]")
                    print(f"  {codigo:<6} ({fila['competicion']:<8} {fila['n_filas']:>3} filas) "
                          f"-> RENOMBRAR a '{nombre_generico}' ({pais}){nota}")
                    if aplicar:
                        try:
                            conn.execute(
                                "UPDATE equipos SET nombre = ?, pais = ? WHERE id = ?;",
                                (nombre_generico, pais, fila["id"]),
                            )
                        except sqlite3.IntegrityError:
                            # Otro código de esta misma pasada ya se renombró a
                            # este mismo nombre (ej. VBC y VIR -> "Virtus
                            # Bologna") - fusionar con ese en vez de duplicar.
                            destino = conn.execute(
                                "SELECT id FROM equipos WHERE nombre = ? AND competicion = ? AND id != ?;",
                                (nombre_generico, fila["competicion"], fila["id"]),
                            ).fetchone()
                            if destino:
                                _reasignar_y_borrar(conn, fila["id"], destino["id"])
                                print(f"    (ya existía - fusionado con id={destino['id']})")
                    n_renombrados += 1
            except Exception as error:
                if aplicar:
                    conn.execute("ROLLBACK TO codigo;")
                print(f"    [error] {codigo} ({fila['competicion']}) - no se pudo procesar: {error}")
                continue
            finally:
                if aplicar:
                    conn.execute("RELEASE codigo;")

        print(
            f"\n{n_fusionados} equipo(s) a fusionar, {n_renombrados} a renombrar "
            f"({'APLICADO' if aplicar else 'sin aplicar - repite con --aplicar'})."
        )

        if sin_mapeo:
            print(
                f"\n{len(sin_mapeo)} código(s) SIN mapeo todavía (de mayor a menor uso - "
                f"añádelos a MAPEO_CODIGOS en este archivo cuando identifiques el club real):"
            )
            for fila in sin_mapeo:
                print(f"  {fila['nombre']:<6} {fila['competicion']:<10} {fila['n_filas']} fila(s)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Reconcilia los equipos provisionales (código como nombre) de Euroliga/EuroCup."
    )
    parser.add_argument(
        "--aplicar", action="store_true",
        help="Aplica los cambios en la base de datos (por defecto solo muestra el informe).",
    )
    args = parser.parse_args()
    reconciliar(args.aplicar)
