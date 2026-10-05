"""
Migración: activa la búsqueda de texto libre (FTS5) sobre los campos de
texto libre repartidos en varias tablas (lesiones, datos_economicos,
jugadores, trayectoria, hitos_carrera) - p.ej. buscar "rodilla" y que
aparezca cualquier jugador con eso en el diagnóstico, la zona corporal o el
tratamiento de alguna lesión, sin tener que saber de antemano en qué campo
está.

Por qué una tabla FTS5 aparte en vez de "content=" enlazado a una sola
tabla: los campos que nos interesa poder buscar a la vez viven en CINCO
tablas distintas, y FTS5 con content= solo puede enlazarse a una tabla
fuente. En su lugar, esta migración crea una tabla FTS5 independiente
(busqueda_texto) que, por cada fila relevante de esas cinco tablas,
concatena sus columnas de texto libre en un solo campo "contenido", junto
con de qué tabla/fila/jugador viene (para poder enlazar el resultado de
vuelta a la ficha del jugador). Se mantiene sincronizada automáticamente
con triggers AFTER INSERT/UPDATE/DELETE en cada tabla fuente - un alta,
edición o baja normal (manual o por scraping) ya actualiza el índice sin
tocar nada más.

Columnas de texto libre indexadas:
  - lesiones: tipo_lesion, zona_corporal, diagnostico, tratamiento, notas
  - datos_economicos: agente_representante, notas
  - jugadores: agente_representante
  - trayectoria: rol
  - hitos_carrera: tipo, descripcion

Tokenizador: se intenta "unicode61 remove_diacritics 2" (ignora tildes al
buscar - "lesion" encuentra "lesión" - necesita SQLite >= 3.27), con dos
alternativas más limitadas si esa no está disponible en esta instalación de
Python/SQLite (ver _TOKENIZERS_A_PROBAR). Si ninguna funciona (módulo FTS5
no compilado), la migración avisa y no hace nada - la app detecta que la
tabla no existe y lo indica en la propia página de búsqueda en vez de fallar.

Uso (una sola vez; es idempotente - si la tabla ya existe, no hace nada):
    python -m database.migrar_fts_busqueda_v7
"""
import sqlite3

from config import DB_PATH

_TOKENIZERS_A_PROBAR = [
    "unicode61 remove_diacritics 2",
    "unicode61 remove_diacritics 1",
    "unicode61",
]

# (tabla fuente, columna que apunta al jugador, columnas de texto libre a concatenar)
_FUENTES = [
    ("lesiones", "jugador_id", ["tipo_lesion", "zona_corporal", "diagnostico", "tratamiento", "notas"]),
    ("datos_economicos", "jugador_id", ["agente_representante", "notas"]),
    ("jugadores", "id", ["agente_representante"]),
    ("trayectoria", "jugador_id", ["rol"]),
    ("hitos_carrera", "jugador_id", ["tipo", "descripcion"]),
]


def _tabla_existe(conn: sqlite3.Connection, nombre: str) -> bool:
    fila = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?;", (nombre,)
    ).fetchone()
    return fila is not None


def _concat_sql(prefijo: str, columnas: list[str]) -> str:
    """('NEW', ['a', 'b']) -> "COALESCE(NEW.a, '') || ' ' || COALESCE(NEW.b, '')"."""
    return " || ' ' || ".join(f"COALESCE({prefijo}.{columna}, '')" for columna in columnas)


def _crear_tabla_fts(conn: sqlite3.Connection) -> str:
    """Prueba los tokenizadores de _TOKENIZERS_A_PROBAR de más a menos
    capaz; devuelve el primero que funciona. Lanza RuntimeError si FTS5 no
    está disponible en absoluto en esta instalación."""
    for tokenizer in _TOKENIZERS_A_PROBAR:
        try:
            conn.execute(
                f"""
                CREATE VIRTUAL TABLE busqueda_texto USING fts5(
                    contenido,
                    tabla UNINDEXED,
                    registro_id UNINDEXED,
                    jugador_id UNINDEXED,
                    tokenize = "{tokenizer}"
                );
                """
            )
            return tokenizer
        except sqlite3.OperationalError:
            continue
    raise RuntimeError(
        "No se pudo crear la tabla FTS5 con ningún tokenizador - "
        "probablemente esta instalación de Python/SQLite no tiene compilado "
        "el módulo FTS5. La búsqueda de texto libre no estará disponible; "
        "el resto de la aplicación sigue funcionando con normalidad."
    )


def _crear_triggers(conn: sqlite3.Connection) -> None:
    for tabla, jugador_id_expr, columnas in _FUENTES:
        contenido_new = _concat_sql("NEW", columnas)

        conn.execute(f"""
            CREATE TRIGGER trg_{tabla}_fts_ai AFTER INSERT ON {tabla} BEGIN
                INSERT INTO busqueda_texto (contenido, tabla, registro_id, jugador_id)
                VALUES ({contenido_new}, '{tabla}', NEW.id, NEW.{jugador_id_expr});
            END;
        """)

        conn.execute(f"""
            CREATE TRIGGER trg_{tabla}_fts_au AFTER UPDATE ON {tabla} BEGIN
                DELETE FROM busqueda_texto WHERE tabla = '{tabla}' AND registro_id = OLD.id;
                INSERT INTO busqueda_texto (contenido, tabla, registro_id, jugador_id)
                VALUES ({contenido_new}, '{tabla}', NEW.id, NEW.{jugador_id_expr});
            END;
        """)

        conn.execute(f"""
            CREATE TRIGGER trg_{tabla}_fts_ad AFTER DELETE ON {tabla} BEGIN
                DELETE FROM busqueda_texto WHERE tabla = '{tabla}' AND registro_id = OLD.id;
            END;
        """)


def _poblar_inicial(conn: sqlite3.Connection) -> int:
    """Indexa lo que ya hubiera en la base de datos antes de activar esta
    migración (los triggers solo cubren altas/ediciones/bajas a partir de
    ahora)."""
    total = 0
    for tabla, jugador_id_expr, columnas in _FUENTES:
        contenido_select = " || ' ' || ".join(f"COALESCE({columna}, '')" for columna in columnas)
        filas = conn.execute(
            f"SELECT id, {jugador_id_expr} AS jugador_id, {contenido_select} AS contenido FROM {tabla};"
        ).fetchall()
        for fila_id, jugador_id, contenido in filas:
            conn.execute(
                "INSERT INTO busqueda_texto (contenido, tabla, registro_id, jugador_id) VALUES (?, ?, ?, ?);",
                (contenido, tabla, fila_id, jugador_id),
            )
            total += 1
    return total


def migrar() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        if _tabla_existe(conn, "busqueda_texto"):
            print("La tabla 'busqueda_texto' (FTS5) ya existía. Nada que hacer.")
            return

        try:
            tokenizer_usado = _crear_tabla_fts(conn)
        except RuntimeError as error:
            print(f"[aviso] {error}")
            return

        _crear_triggers(conn)
        total = _poblar_inicial(conn)
        conn.commit()

        print(f"Tabla 'busqueda_texto' creada (tokenizador: {tokenizer_usado}).")
        print(f"Triggers de sincronización creados para: {', '.join(t for t, _, _ in _FUENTES)}.")
        print(f"{total} fila(s) indexada(s) inicialmente.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrar()
