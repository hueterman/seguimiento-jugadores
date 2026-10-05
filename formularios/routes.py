"""
Rutas de la aplicación de formularios manuales.
"""
from flask import Blueprint, render_template, request, redirect, url_for
from markupsafe import Markup, escape

from db.conexion import get_connection, listar_catalogo

routes = Blueprint("routes", __name__)

# Etiquetas legibles para cada tabla fuente que indexa
# database/migrar_fts_busqueda_v7.py en busqueda_texto.
_ETIQUETAS_TABLA_BUSQUEDA = {
    "lesiones": "Lesión",
    "datos_economicos": "Dato económico",
    "trayectoria": "Trayectoria",
    "hitos_carrera": "Hito de carrera",
    "jugadores": "Datos personales",
}


def _construir_consulta_fts(texto: str) -> str:
    """Convierte el texto escrito por el usuario en una expresión MATCH de
    FTS5 segura: cada palabra se escapa entre comillas dobles (así nunca se
    interpreta como operador de FTS5 - ':', '-', '*', 'AND'...) y se le
    añade un comodín de prefijo, combinando todas las palabras con AND
    (todas tienen que aparecer, en cualquier campo/fila). Devuelve '' si no
    queda ninguna palabra."""
    partes = []
    for palabra in texto.split():
        escapada = palabra.replace('"', '""')
        if escapada:
            partes.append(f'"{escapada}"*')
    return " AND ".join(partes)


def _resaltar_fragmento(fragmento: str) -> Markup:
    """snippet() de FTS5 (ver buscar_texto) marca las coincidencias con los
    delimitadores '[[' y ']]' (elegidos por no colisionar con HTML/Jinja);
    esto los convierte en <mark>, escapando todo lo demás para que un
    diagnóstico o nota con caracteres raros no se interprete como HTML."""
    resultado = Markup("")
    trozos = fragmento.split("[[")
    resultado += escape(trozos[0])
    for trozo in trozos[1:]:
        if "]]" in trozo:
            resaltado, resto = trozo.split("]]", 1)
            resultado += Markup("<mark>") + escape(resaltado) + Markup("</mark>") + escape(resto)
        else:
            resultado += escape(trozo)
    return resultado


def _contexto_resultado_busqueda(conn, tabla: str, registro_id: int) -> str:
    """Una línea de contexto legible para un resultado de buscar_texto,
    consultando la fila concreta donde coincidió (lesión, dato económico...)
    para no depender solo del fragmento de texto suelto."""
    if tabla == "lesiones":
        fila = conn.execute(
            "SELECT fecha_inicio, tipo_lesion, zona_corporal FROM lesiones WHERE id = ?;",
            (registro_id,),
        ).fetchone()
        if fila:
            detalle = " - ".join(p for p in (fila["tipo_lesion"], fila["zona_corporal"]) if p) or "sin detalle"
            fecha = f"{fila['fecha_inicio']}: " if fila["fecha_inicio"] else ""
            return f"{fecha}{detalle}"
    elif tabla == "datos_economicos":
        fila = conn.execute(
            "SELECT d.temporada, eq.nombre AS equipo FROM datos_economicos d "
            "LEFT JOIN equipos eq ON eq.id = d.equipo_id WHERE d.id = ?;",
            (registro_id,),
        ).fetchone()
        if fila:
            return f"{fila['temporada']} ({fila['equipo'] or 'sin equipo'})"
    elif tabla == "trayectoria":
        fila = conn.execute(
            "SELECT t.temporada, eq.nombre AS equipo FROM trayectoria t "
            "LEFT JOIN equipos eq ON eq.id = t.equipo_id WHERE t.id = ?;",
            (registro_id,),
        ).fetchone()
        if fila:
            return f"{fila['temporada']} en {fila['equipo'] or '-'}"
    elif tabla == "hitos_carrera":
        fila = conn.execute(
            "SELECT temporada, tipo FROM hitos_carrera WHERE id = ?;", (registro_id,)
        ).fetchone()
        if fila:
            return f"{fila['tipo'] or '-'} ({fila['temporada'] or 'sin temporada'})"
    elif tabla == "jugadores":
        return "agente representante"
    return ""


@routes.route("/buscar")
def buscar_texto():
    """Búsqueda de texto libre (FTS5) sobre todos los campos de texto libre
    del proyecto a la vez: lesiones (tipo, zona, diagnóstico, tratamiento,
    notas), datos económicos (agente, notas), trayectoria (rol), hitos de
    carrera (tipo, descripción) y agente representante del jugador. Hace
    falta haber ejecutado una vez `python -m database.migrar_fts_busqueda_v7`
    (ver ese fichero); si la tabla FTS5 'busqueda_texto' no existe todavía,
    esta página lo indica en vez de fallar con un error de SQL."""
    texto = request.args.get("q", "").strip()
    resultados = []

    with get_connection() as conn:
        disponible = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'busqueda_texto';"
        ).fetchone() is not None

        if disponible and texto:
            consulta_fts = _construir_consulta_fts(texto)
            if consulta_fts:
                filas = conn.execute(
                    """
                    SELECT bt.tabla, bt.registro_id, bt.jugador_id, j.nombre, j.apellidos,
                           snippet(busqueda_texto, 0, '[[', ']]', '…', 10) AS fragmento
                    FROM busqueda_texto bt
                    JOIN jugadores j ON j.id = bt.jugador_id
                    WHERE busqueda_texto MATCH ?
                    ORDER BY rank
                    LIMIT 100;
                    """,
                    (consulta_fts,),
                ).fetchall()
                for fila in filas:
                    resultados.append({
                        "jugador_id": fila["jugador_id"],
                        "nombre": fila["nombre"],
                        "apellidos": fila["apellidos"],
                        "etiqueta_tabla": _ETIQUETAS_TABLA_BUSQUEDA.get(fila["tabla"], fila["tabla"]),
                        "contexto": _contexto_resultado_busqueda(conn, fila["tabla"], fila["registro_id"]),
                        "fragmento": _resaltar_fragmento(fila["fragmento"]),
                    })

    return render_template(
        "buscar_texto.html", texto=texto, resultados=resultados, disponible=disponible,
    )


# Métricas disponibles para la búsqueda avanzada por estadísticas
# (routes.buscar_estadisticas). Es el ÚNICO whitelist de columnas que se usa
# para construir el SQL de ese filtro - lo que venga de la query string
# nunca se interpola directamente como nombre de columna, solo como valor
# parametrizado. Añadir una métrica nueva es añadir una tupla aquí.
METRICAS_ESTADISTICAS = [
    ("partidos_jugados", "Partidos jugados"),
    ("minutos_promedio", "Minutos (promedio)"),
    ("puntos_promedio", "Puntos (promedio)"),
    ("puntos_max", "Puntos (máx. en un partido)"),
    ("rebotes_promedio", "Rebotes (promedio)"),
    ("asistencias_promedio", "Asistencias (promedio)"),
    ("robos_totales", "Robos (total temporada)"),
    ("tapones_totales", "Tapones (total temporada)"),
    ("perdidas_totales", "Pérdidas (total temporada)"),
    ("porcentaje_tiro2", "% Tiro de 2"),
    ("porcentaje_tiro3", "% Tiro de 3"),
    ("porcentaje_tiro_libre", "% Tiro libre"),
    ("mas_menos_promedio", "+/- (promedio)"),
    ("valoracion_pir", "Valoración (PIR)"),
]
_METRICAS_VALIDAS = {clave for clave, _ in METRICAS_ESTADISTICAS}


@routes.route("/")
def index():
    """Listado de jugadores con buscador de texto libre (nombre, apellidos,
    nacionalidad o equipo actual) + filtros estructurados (posición, estado,
    nacionalidad, equipo actual, rango de altura y de edad). Todos los
    filtros son opcionales y se combinan con AND; se leen de la query string
    (GET) para que el resultado se pueda enlazar/recargar sin perderse."""
    filtros = {
        "q": request.args.get("q", "").strip(),
        "posicion_id": request.args.get("posicion_id", type=int),
        "estado_id": request.args.get("estado_id", type=int),
        "nacionalidad": request.args.get("nacionalidad", "").strip(),
        "equipo_id": request.args.get("equipo_id", type=int),
        "altura_min": request.args.get("altura_min", type=int),
        "altura_max": request.args.get("altura_max", type=int),
        "edad_min": request.args.get("edad_min", type=int),
        "edad_max": request.args.get("edad_max", type=int),
    }

    condiciones = []
    parametros: list = []

    if filtros["q"]:
        comodin = f"%{filtros['q']}%"
        condiciones.append(
            """(
                j.nombre LIKE ? OR j.apellidos LIKE ? OR j.nacionalidad LIKE ?
                OR EXISTS (
                    SELECT 1 FROM trayectoria t JOIN equipos eq ON eq.id = t.equipo_id
                    WHERE t.jugador_id = j.id AND t.fecha_fin IS NULL AND eq.nombre LIKE ?
                )
            )"""
        )
        parametros += [comodin, comodin, comodin, comodin]

    if filtros["posicion_id"]:
        condiciones.append("j.posicion_id = ?")
        parametros.append(filtros["posicion_id"])

    if filtros["estado_id"]:
        condiciones.append("j.estado_actual_id = ?")
        parametros.append(filtros["estado_id"])

    if filtros["nacionalidad"]:
        condiciones.append("j.nacionalidad = ?")
        parametros.append(filtros["nacionalidad"])

    if filtros["equipo_id"]:
        condiciones.append(
            "EXISTS (SELECT 1 FROM trayectoria t WHERE t.jugador_id = j.id "
            "AND t.fecha_fin IS NULL AND t.equipo_id = ?)"
        )
        parametros.append(filtros["equipo_id"])

    if filtros["altura_min"] is not None:
        condiciones.append("j.altura_cm >= ?")
        parametros.append(filtros["altura_min"])

    if filtros["altura_max"] is not None:
        condiciones.append("j.altura_cm <= ?")
        parametros.append(filtros["altura_max"])

    # Edad -> rango de fecha_nacimiento (aproximado al día, suficiente para un filtro).
    if filtros["edad_min"] is not None:
        condiciones.append("j.fecha_nacimiento <= date('now', ?)")
        parametros.append(f"-{filtros['edad_min']} years")

    if filtros["edad_max"] is not None:
        condiciones.append("j.fecha_nacimiento >= date('now', ?)")
        parametros.append(f"-{filtros['edad_max'] + 1} years")

    where_sql = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""

    with get_connection() as conn:
        jugadores = conn.execute(
            f"""
            SELECT j.id, j.nombre, j.apellidos, p.nombre AS posicion,
                   e.nombre AS estado, j.nacionalidad, j.altura_cm,
                   (
                       SELECT eq.nombre FROM trayectoria t
                       JOIN equipos eq ON eq.id = t.equipo_id
                       WHERE t.jugador_id = j.id AND t.fecha_fin IS NULL
                       ORDER BY t.temporada DESC LIMIT 1
                   ) AS equipo_actual
            FROM jugadores j
            LEFT JOIN posiciones p ON p.id = j.posicion_id
            LEFT JOIN estados_jugador e ON e.id = j.estado_actual_id
            {where_sql}
            ORDER BY j.apellidos, j.nombre;
            """,
            parametros,
        ).fetchall()

        posiciones = listar_catalogo("posiciones")
        estados = listar_catalogo("estados_jugador")
        nacionalidades = [
            fila["nacionalidad"]
            for fila in conn.execute(
                "SELECT DISTINCT nacionalidad FROM jugadores "
                "WHERE nacionalidad IS NOT NULL ORDER BY nacionalidad;"
            ).fetchall()
        ]
        # Solo equipos con algún jugador actualmente en plantilla (fecha_fin
        # NULL en trayectoria), para no llenar el desplegable de equipos
        # históricos sin jugadores activos.
        equipos = conn.execute(
            """
            SELECT DISTINCT eq.id, eq.nombre, eq.competicion
            FROM equipos eq
            JOIN trayectoria t ON t.equipo_id = eq.id
            WHERE t.fecha_fin IS NULL
            ORDER BY eq.nombre, eq.competicion;
            """
        ).fetchall()

    return render_template(
        "index.html",
        jugadores=jugadores,
        filtros=filtros,
        posiciones=posiciones,
        estados=estados,
        nacionalidades=nacionalidades,
        equipos=equipos,
    )


@routes.route("/estadisticas/buscar")
def buscar_estadisticas():
    """Búsqueda avanzada sobre estadisticas_temporada: filtra por
    temporada/competición y por rango (mínimo/máximo) de cualquier métrica
    de METRICAS_ESTADISTICAS, y permite ordenar el resultado por cualquiera
    de ellas. Trabaja sobre filas por temporada (no sobre los agregados de
    estadisticas_carrera), así que un mismo jugador puede aparecer varias
    veces si varias de sus temporadas cumplen el filtro."""
    temporada = request.args.get("temporada", "").strip()
    competicion = request.args.get("competicion", "").strip()
    orden = request.args.get("orden", "valoracion_pir").strip()
    if orden not in _METRICAS_VALIDAS:
        orden = "valoracion_pir"

    filtros_rango = {
        clave: (
            request.args.get(f"{clave}_min", type=float),
            request.args.get(f"{clave}_max", type=float),
        )
        for clave, _ in METRICAS_ESTADISTICAS
    }

    condiciones = []
    parametros: list = []

    if temporada:
        condiciones.append("et.temporada = ?")
        parametros.append(temporada)

    if competicion:
        condiciones.append("et.competicion = ?")
        parametros.append(competicion)

    for clave, (v_min, v_max) in filtros_rango.items():
        if v_min is not None:
            condiciones.append(f"et.{clave} >= ?")
            parametros.append(v_min)
        if v_max is not None:
            condiciones.append(f"et.{clave} <= ?")
            parametros.append(v_max)

    where_sql = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""

    with get_connection() as conn:
        resultados = conn.execute(
            f"""
            SELECT j.id AS jugador_id, j.nombre, j.apellidos, p.nombre AS posicion,
                   et.temporada, et.competicion, eq.nombre AS equipo,
                   et.partidos_jugados, et.minutos_promedio, et.puntos_promedio, et.puntos_max,
                   et.rebotes_promedio, et.asistencias_promedio, et.robos_totales,
                   et.tapones_totales, et.perdidas_totales,
                   et.porcentaje_tiro2, et.porcentaje_tiro3, et.porcentaje_tiro_libre,
                   et.mas_menos_promedio, et.valoracion_pir
            FROM estadisticas_temporada et
            JOIN jugadores j ON j.id = et.jugador_id
            LEFT JOIN posiciones p ON p.id = j.posicion_id
            LEFT JOIN equipos eq ON eq.id = et.equipo_id
            {where_sql}
            ORDER BY et.{orden} DESC, j.apellidos, j.nombre
            LIMIT 200;
            """,
            parametros,
        ).fetchall()

        temporadas = [
            fila["temporada"]
            for fila in conn.execute(
                "SELECT DISTINCT temporada FROM estadisticas_temporada ORDER BY temporada DESC;"
            ).fetchall()
        ]
        competiciones = [
            fila["competicion"]
            for fila in conn.execute(
                "SELECT DISTINCT competicion FROM estadisticas_temporada "
                "WHERE competicion IS NOT NULL ORDER BY competicion;"
            ).fetchall()
        ]

    return render_template(
        "buscar_estadisticas.html",
        resultados=resultados,
        filtros={"temporada": temporada, "competicion": competicion, "orden": orden},
        filtros_rango=filtros_rango,
        metricas=METRICAS_ESTADISTICAS,
        temporadas=temporadas,
        competiciones=competiciones,
    )


@routes.route("/jugadores/<int:jugador_id>")
def detalle_jugador(jugador_id):
    with get_connection() as conn:
        jugador = conn.execute(
            """
            SELECT j.*, p.nombre AS posicion, e.nombre AS estado
            FROM jugadores j
            LEFT JOIN posiciones p ON p.id = j.posicion_id
            LEFT JOIN estados_jugador e ON e.id = j.estado_actual_id
            WHERE j.id = ?;
            """,
            (jugador_id,),
        ).fetchone()

        trayectoria = conn.execute(
            """
            SELECT t.temporada, eq.nombre AS equipo, tm.nombre AS tipo_movimiento,
                   t.fecha_inicio, t.fecha_fin, t.dorsal, t.rol
            FROM trayectoria t
            JOIN equipos eq ON eq.id = t.equipo_id
            LEFT JOIN tipos_movimiento tm ON tm.id = t.tipo_movimiento_id
            WHERE t.jugador_id = ?
            ORDER BY t.temporada DESC;
            """,
            (jugador_id,),
        ).fetchall()

        estadisticas = conn.execute(
            """
            SELECT et.temporada, eq.nombre AS equipo, et.competicion,
                   et.partidos_jugados, et.partidos_titular,
                   et.puntos_promedio, et.puntos_max,
                   et.rebotes_promedio, et.rebotes_ofensivos_totales, et.rebotes_defensivos_totales,
                   et.asistencias_promedio,
                   et.t2_convertidos, et.t2_intentados, et.porcentaje_tiro2,
                   et.t3_convertidos, et.t3_intentados, et.porcentaje_tiro3,
                   et.tl_convertidos, et.tl_intentados, et.porcentaje_tiro_libre,
                   et.robos_totales, et.tapones_totales, et.perdidas_totales, et.faltas_totales,
                   et.mas_menos_promedio, et.valoracion_pir, et.victorias, et.derrotas
            FROM estadisticas_temporada et
            LEFT JOIN equipos eq ON eq.id = et.equipo_id
            WHERE et.jugador_id = ?
            ORDER BY et.temporada DESC;
            """,
            (jugador_id,),
        ).fetchall()

        carrera = conn.execute(
            """
            SELECT competicion, tipo_fila, partidos_jugados, partidos_titular,
                   minutos, puntos, puntos_max,
                   t2_convertidos, t2_intentados, porcentaje_tiro2,
                   t3_convertidos, t3_intentados, porcentaje_tiro3,
                   tl_convertidos, tl_intentados, porcentaje_tiro_libre,
                   rebotes_ofensivos, rebotes_defensivos, rebotes,
                   asistencias, robos, tapones_favor, tapones_contra, mates,
                   perdidas, faltas_cometidas, faltas_recibidas,
                   mas_menos, valoracion_pir, victorias, derrotas
            FROM estadisticas_carrera
            WHERE jugador_id = ?
            ORDER BY competicion, tipo_fila;
            """,
            (jugador_id,),
        ).fetchall()

        lesiones = conn.execute(
            """
            SELECT l.fecha_inicio, l.fecha_fin_real, l.fecha_fin_estimada,
                   l.tipo_lesion, l.zona_corporal, g.nombre AS gravedad,
                   el.nombre AS estado
            FROM lesiones l
            LEFT JOIN grados_gravedad g ON g.id = l.gravedad_id
            LEFT JOIN estados_lesion el ON el.id = l.estado_id
            WHERE l.jugador_id = ?
            ORDER BY l.fecha_inicio DESC;
            """,
            (jugador_id,),
        ).fetchall()

        economicos = conn.execute(
            """
            SELECT d.temporada, eq.nombre AS equipo, tc.nombre AS tipo_contrato,
                   d.salario_estimado, d.moneda, nf.nombre AS fiabilidad
            FROM datos_economicos d
            LEFT JOIN equipos eq ON eq.id = d.equipo_id
            LEFT JOIN tipos_contrato tc ON tc.id = d.tipo_contrato_id
            LEFT JOIN niveles_fiabilidad nf ON nf.id = d.fiabilidad_id
            WHERE d.jugador_id = ?
            ORDER BY d.temporada DESC;
            """,
            (jugador_id,),
        ).fetchall()

    return render_template(
        "detalle_jugador.html",
        jugador=jugador,
        trayectoria=trayectoria,
        estadisticas=estadisticas,
        carrera=carrera,
        lesiones=lesiones,
        economicos=economicos,
    )


@routes.route("/entrenadores")
def entrenadores():
    with get_connection() as conn:
        filas = conn.execute(
            """
            SELECT e.nombre, e.apellidos, e.cargo, e.temporada,
                   eq.nombre AS equipo
            FROM entrenadores e
            LEFT JOIN equipos eq ON eq.id = e.equipo_id
            ORDER BY eq.nombre, e.temporada DESC,
                     CASE WHEN e.cargo = 'Entrenador' THEN 0 ELSE 1 END,
                     e.apellidos;
            """
        ).fetchall()
    return render_template("entrenadores.html", entrenadores=filas)


@routes.route("/jugadores/<int:jugador_id>/editar", methods=["GET", "POST"])
def editar_jugador(jugador_id):
    with get_connection() as conn:
        jugador = conn.execute(
            "SELECT * FROM jugadores WHERE id = ?;", (jugador_id,)
        ).fetchone()
    if jugador is None:
        return redirect(url_for("routes.index"))

    if request.method == "POST":
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE jugadores SET
                    nombre = ?, apellidos = ?, fecha_nacimiento = ?, nacionalidad = ?,
                    posicion_id = ?, altura_cm = ?, peso_kg = ?, mano_dominante_id = ?,
                    estado_actual_id = ?, fecha_actualizacion = datetime('now')
                WHERE id = ?;
                """,
                (
                    request.form["nombre"],
                    request.form["apellidos"],
                    request.form.get("fecha_nacimiento") or None,
                    request.form.get("nacionalidad") or None,
                    request.form.get("posicion_id") or None,
                    request.form.get("altura_cm") or None,
                    request.form.get("peso_kg") or None,
                    request.form.get("mano_dominante_id") or None,
                    request.form.get("estado_actual_id") or 1,
                    jugador_id,
                ),
            )
        return redirect(url_for("routes.detalle_jugador", jugador_id=jugador_id))

    posiciones = listar_catalogo("posiciones")
    manos = listar_catalogo("manos_dominantes")
    estados = listar_catalogo("estados_jugador")
    return render_template(
        "editar_jugador.html", jugador=jugador, posiciones=posiciones, manos=manos, estados=estados
    )


@routes.route("/equipos/nuevo", methods=["GET", "POST"])
def nuevo_equipo():
    if request.method == "POST":
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO equipos (nombre, pais, ciudad, competicion, nivel)
                VALUES (?, ?, ?, ?, ?);
                """,
                (
                    request.form["nombre"],
                    request.form.get("pais") or None,
                    request.form.get("ciudad") or None,
                    request.form.get("competicion") or None,
                    request.form.get("nivel") or None,
                ),
            )
        return redirect(url_for("routes.index"))
    return render_template("nuevo_equipo.html")


@routes.route("/jugadores/nuevo", methods=["GET", "POST"])
def nuevo_jugador():
    if request.method == "POST":
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO jugadores
                    (nombre, apellidos, fecha_nacimiento, nacionalidad,
                     posicion_id, altura_cm, peso_kg, mano_dominante_id,
                     estado_actual_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    request.form["nombre"],
                    request.form["apellidos"],
                    request.form.get("fecha_nacimiento") or None,
                    request.form.get("nacionalidad") or None,
                    request.form.get("posicion_id") or None,
                    request.form.get("altura_cm") or None,
                    request.form.get("peso_kg") or None,
                    request.form.get("mano_dominante_id") or None,
                    request.form.get("estado_actual_id") or 1,
                ),
            )
        return redirect(url_for("routes.index"))

    posiciones = listar_catalogo("posiciones")
    manos = listar_catalogo("manos_dominantes")
    estados = listar_catalogo("estados_jugador")
    return render_template(
        "nuevo_jugador.html", posiciones=posiciones, manos=manos, estados=estados
    )


@routes.route("/lesiones/nueva", methods=["GET", "POST"])
def nueva_lesion():
    with get_connection() as conn:
        jugadores = conn.execute(
            "SELECT id, nombre, apellidos FROM jugadores ORDER BY apellidos;"
        ).fetchall()

    if request.method == "POST":
        jugador_id = request.form["jugador_id"]
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO lesiones
                    (jugador_id, fecha_inicio, fecha_fin_estimada, tipo_lesion,
                     zona_corporal, gravedad_id, diagnostico, tratamiento,
                     estado_id, fuente_id, fiabilidad_id, url_fuente, notas)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    jugador_id,
                    request.form["fecha_inicio"],
                    request.form.get("fecha_fin_estimada") or None,
                    request.form.get("tipo_lesion") or None,
                    request.form.get("zona_corporal") or None,
                    request.form.get("gravedad_id") or None,
                    request.form.get("diagnostico") or None,
                    request.form.get("tratamiento") or None,
                    request.form.get("estado_id") or 1,
                    request.form.get("fuente_id") or 1,
                    request.form.get("fiabilidad_id") or 1,
                    request.form.get("url_fuente") or None,
                    request.form.get("notas") or None,
                ),
            )
        return redirect(url_for("routes.detalle_jugador", jugador_id=jugador_id))

    gravedades = listar_catalogo("grados_gravedad")
    estados_lesion = listar_catalogo("estados_lesion")
    fuentes = listar_catalogo("fuentes")
    fiabilidades = listar_catalogo("niveles_fiabilidad")
    jugador_preseleccionado = request.args.get("jugador_id", type=int)
    return render_template(
        "nueva_lesion.html",
        jugadores=jugadores,
        gravedades=gravedades,
        estados_lesion=estados_lesion,
        fuentes=fuentes,
        fiabilidades=fiabilidades,
        jugador_preseleccionado=jugador_preseleccionado,
    )


@routes.route("/economicos/nuevo", methods=["GET", "POST"])
def nuevo_dato_economico():
    with get_connection() as conn:
        jugadores = conn.execute(
            "SELECT id, nombre, apellidos FROM jugadores ORDER BY apellidos;"
        ).fetchall()
        equipos = conn.execute("SELECT id, nombre FROM equipos ORDER BY nombre;").fetchall()

    if request.method == "POST":
        jugador_id = request.form["jugador_id"]
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO datos_economicos
                    (jugador_id, equipo_id, temporada, tipo_contrato_id,
                     salario_estimado, moneda, fecha_inicio_contrato,
                     fecha_fin_contrato, clausula_rescision,
                     agente_representante, fuente_id, fiabilidad_id,
                     url_fuente, notas)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    jugador_id,
                    request.form.get("equipo_id") or None,
                    request.form["temporada"],
                    request.form.get("tipo_contrato_id") or None,
                    request.form.get("salario_estimado") or None,
                    request.form.get("moneda") or "EUR",
                    request.form.get("fecha_inicio_contrato") or None,
                    request.form.get("fecha_fin_contrato") or None,
                    request.form.get("clausula_rescision") or None,
                    request.form.get("agente_representante") or None,
                    request.form.get("fuente_id") or 1,
                    request.form.get("fiabilidad_id") or 2,
                    request.form.get("url_fuente") or None,
                    request.form.get("notas") or None,
                ),
            )
        return redirect(url_for("routes.detalle_jugador", jugador_id=jugador_id))

    tipos_contrato = listar_catalogo("tipos_contrato")
    fuentes = listar_catalogo("fuentes")
    fiabilidades = listar_catalogo("niveles_fiabilidad")
    jugador_preseleccionado = request.args.get("jugador_id", type=int)
    return render_template(
        "nuevo_dato_economico.html",
        jugadores=jugadores,
        equipos=equipos,
        tipos_contrato=tipos_contrato,
        fuentes=fuentes,
        fiabilidades=fiabilidades,
        jugador_preseleccionado=jugador_preseleccionado,
    )
