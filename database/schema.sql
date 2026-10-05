-- Esquema: seguimiento_jugadores (SQLite)
-- Proyecto independiente y autocontenido: sin dependencias ni referencias
-- a ninguna otra base de datos ni proyecto.
-- Todos los campos de valores cerrados son tablas de catálogo (editables desde la interfaz sin tocar el esquema)

PRAGMA foreign_keys = ON;

-- ============================================================
-- CATÁLOGOS CERRADOS
-- ============================================================

CREATE TABLE posiciones (
    id     INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);

INSERT INTO posiciones (nombre) VALUES
    ('Base'), ('Escolta'), ('Alero'), ('Ala-pívot'), ('Pívot');

CREATE TABLE tipos_movimiento (
    id     INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);

INSERT INTO tipos_movimiento (nombre) VALUES
    ('Fichaje libre'), ('Traspaso'), ('Cesión'), ('Fin de cesión'),
    ('Renovación'), ('Cantera'), ('Draft');

CREATE TABLE manos_dominantes (
    id     INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);

INSERT INTO manos_dominantes (nombre) VALUES
    ('Izquierda'), ('Derecha'), ('Ambidiestro');

CREATE TABLE estados_jugador (
    id     INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);

INSERT INTO estados_jugador (nombre) VALUES
    ('Activo'), ('Lesionado'), ('Sin equipo'), ('Retirado');

-- Catálogo compartido: de dónde sale un dato (estadísticas, lesiones, económicos)
CREATE TABLE fuentes (
    id     INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);

INSERT INTO fuentes (nombre) VALUES
    ('Manual'), ('Scraping'), ('Prensa'), ('Estimado');

-- Catálogo compartido: cuánto nos fiamos de un dato (lesiones, económicos)
CREATE TABLE niveles_fiabilidad (
    id     INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);

INSERT INTO niveles_fiabilidad (nombre) VALUES
    ('Confirmado'), ('Estimado'), ('Rumor');

CREATE TABLE grados_gravedad (
    id     INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);

INSERT INTO grados_gravedad (nombre) VALUES
    ('Leve'), ('Moderada'), ('Grave');

CREATE TABLE estados_lesion (
    id     INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);

INSERT INTO estados_lesion (nombre) VALUES
    ('En tratamiento'), ('Recuperado'), ('Recaída');

CREATE TABLE tipos_contrato (
    id     INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);

INSERT INTO tipos_contrato (nombre) VALUES
    ('Profesional'), ('Cantera'), ('Cesión'), ('Dos vías');

-- ============================================================
-- EQUIPOS
-- ============================================================

CREATE TABLE equipos (
    id          INTEGER PRIMARY KEY,
    nombre      TEXT NOT NULL,
    pais        TEXT,
    ciudad      TEXT,
    competicion TEXT,
    nivel       TEXT,
    UNIQUE (nombre, competicion)
);

-- ============================================================
-- JUGADORES
-- ============================================================

CREATE TABLE jugadores (
    id                      INTEGER PRIMARY KEY,
    nombre                  TEXT NOT NULL,
    apellidos               TEXT NOT NULL,
    fecha_nacimiento        DATE,
    nacionalidad            TEXT,
    posicion_id             INTEGER REFERENCES posiciones(id),
    altura_cm               INTEGER,
    peso_kg                 INTEGER,
    mano_dominante_id       INTEGER REFERENCES manos_dominantes(id),
    fecha_debut_profesional DATE,
    estado_actual_id        INTEGER NOT NULL DEFAULT 1 REFERENCES estados_jugador(id), -- 1 = Activo
    agente_representante    TEXT,
    foto_url                TEXT,
    id_externo_acb          TEXT,  -- id numérico de la ficha del jugador en acb.com (fuente del scraper)
    id_externo_euroleague   TEXT,  -- "person.code" en la API de Euroliga/EuroCup (columna separada de
                                   -- id_externo_acb: un jugador puede tener ambas si juega las dos competiciones)
    fecha_creacion          TEXT NOT NULL DEFAULT (datetime('now')),
    fecha_actualizacion     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_jugadores_posicion ON jugadores(posicion_id);
CREATE INDEX idx_jugadores_estado   ON jugadores(estado_actual_id);

-- ============================================================
-- ENTRENADORES (cuerpo técnico por equipo/temporada)
--
-- Tabla separada de jugadores: acb.com no publica el cuerpo técnico en
-- el HTML que descarga un scraper normal (se carga por JavaScript, ver
-- scraping/equipos.py), así que esto se da de alta a mano/por CSV con
-- scraping/alta_entrenadores.py en vez de scraping automático.
-- ============================================================

CREATE TABLE entrenadores (
    id                  INTEGER PRIMARY KEY,
    nombre              TEXT NOT NULL,
    apellidos           TEXT NOT NULL,
    cargo               TEXT,     -- 'Entrenador', 'Entrenador Ayudante', 'Preparador físico'...
    equipo_id           INTEGER REFERENCES equipos(id),
    temporada           TEXT,     -- ej. "2026-2027"
    id_externo_acb      TEXT,     -- id numérico de su ficha en acb.com, si se conoce
    fuente_id           INTEGER NOT NULL DEFAULT 1 REFERENCES fuentes(id), -- 1 = Manual
    fecha_registro      TEXT NOT NULL DEFAULT (datetime('now')),
    fecha_actualizacion TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (nombre, apellidos, equipo_id, temporada)
);

CREATE INDEX idx_entrenadores_equipo ON entrenadores(equipo_id);

-- ============================================================
-- TRAYECTORIA (equipos por los que ha pasado a lo largo de los años)
-- ============================================================

CREATE TABLE trayectoria (
    id                     INTEGER PRIMARY KEY,
    jugador_id             INTEGER NOT NULL REFERENCES jugadores(id) ON DELETE CASCADE,
    equipo_id              INTEGER NOT NULL REFERENCES equipos(id),
    equipo_procedencia_id  INTEGER REFERENCES equipos(id),
    temporada              TEXT NOT NULL,          -- ej. "2023-2024"
    tipo_movimiento_id     INTEGER REFERENCES tipos_movimiento(id),
    fecha_inicio           DATE,
    fecha_fin              DATE,                    -- NULL si sigue en el equipo
    dorsal                 INTEGER,
    rol                    TEXT,                    -- titular / rotación / banquillo
    fecha_registro         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_trayectoria_jugador ON trayectoria(jugador_id);
CREATE INDEX idx_trayectoria_equipo  ON trayectoria(equipo_id);
-- Evita duplicados al re-ejecutar el scraper para el mismo jugador/temporada
CREATE UNIQUE INDEX idx_trayectoria_unica ON trayectoria(jugador_id, equipo_id, temporada);

-- ============================================================
-- ESTADÍSTICAS POR TEMPORADA
-- ============================================================

CREATE TABLE estadisticas_temporada (
    id                     INTEGER PRIMARY KEY,
    jugador_id             INTEGER NOT NULL REFERENCES jugadores(id) ON DELETE CASCADE,
    equipo_id              INTEGER REFERENCES equipos(id),
    temporada              TEXT NOT NULL,
    competicion            TEXT,
    partidos_jugados       INTEGER DEFAULT 0,
    partidos_titular       INTEGER DEFAULT 0,  -- "5i" de acb.com (quintetos iniciales) - sentido no confirmado al 100%
    minutos_totales        REAL,
    minutos_promedio       REAL,
    puntos_totales         INTEGER,
    puntos_promedio        REAL,
    puntos_max             INTEGER,            -- máximo de puntos en un partido esa temporada
    t2_convertidos         INTEGER,
    t2_intentados          INTEGER,
    t3_convertidos         INTEGER,
    t3_intentados          INTEGER,
    tl_convertidos         INTEGER,
    tl_intentados          INTEGER,
    rebotes_totales        INTEGER,
    rebotes_promedio       REAL,
    rebotes_ofensivos_totales REAL,            -- estimado: promedio × partidos_jugados
    rebotes_defensivos_totales REAL,           -- estimado: promedio × partidos_jugados
    asistencias_totales    INTEGER,
    asistencias_promedio   REAL,
    robos_totales          INTEGER,
    tapones_totales        INTEGER,            -- tapones puestos (a favor)
    tapones_recibidos_totales REAL,            -- tapones recibidos (en contra) - estimado
    mates_totales          REAL,               -- estimado
    perdidas_totales       INTEGER,
    faltas_totales         INTEGER,            -- faltas cometidas
    faltas_recibidas_totales REAL,             -- estimado
    porcentaje_tiro2       REAL,
    porcentaje_tiro3       REAL,
    porcentaje_tiro_libre  REAL,
    mas_menos_promedio     REAL,
    valoracion_pir         REAL,
    victorias              INTEGER,            -- partidos ganados por el equipo con el jugador en pista, según acb.com
    derrotas               INTEGER,
    fuente_id              INTEGER NOT NULL DEFAULT 1 REFERENCES fuentes(id), -- 1 = Manual
    fecha_actualizacion    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (jugador_id, equipo_id, temporada, competicion)
);

CREATE INDEX idx_estadisticas_jugador ON estadisticas_temporada(jugador_id);

-- ============================================================
-- ESTADÍSTICAS DE CARRERA (agregados "Totales"/"Promedios" que acb.com
-- publica al final de la tabla de temporadas - valores reales de la
-- fuente, no estimaciones nuestras; ver scraping/estadisticas.py)
-- ============================================================

CREATE TABLE estadisticas_carrera (
    id                      INTEGER PRIMARY KEY,
    jugador_id              INTEGER NOT NULL REFERENCES jugadores(id) ON DELETE CASCADE,
    competicion             TEXT,
    tipo_fila               TEXT NOT NULL,  -- 'Totales' o 'Promedios', tal cual lo publica la fuente
    partidos_jugados        REAL,
    partidos_titular        REAL,  -- "5i" de acb.com - sentido no confirmado al 100%
    minutos                 REAL,
    puntos                  REAL,
    puntos_max              REAL,
    t2_convertidos          REAL,
    t2_intentados           REAL,
    porcentaje_tiro2        REAL,
    t3_convertidos          REAL,
    t3_intentados           REAL,
    porcentaje_tiro3        REAL,
    tl_convertidos          REAL,
    tl_intentados           REAL,
    porcentaje_tiro_libre   REAL,
    rebotes_ofensivos       REAL,
    rebotes_defensivos      REAL,
    rebotes                 REAL,
    asistencias             REAL,
    robos                   REAL,
    tapones_favor           REAL,
    tapones_contra          REAL,
    mates                   REAL,
    perdidas                REAL,
    faltas_cometidas        REAL,
    faltas_recibidas        REAL,
    mas_menos                REAL,
    valoracion_pir           REAL,
    victorias                REAL,
    derrotas                 REAL,
    fuente_id                INTEGER NOT NULL DEFAULT 1 REFERENCES fuentes(id), -- 1 = Manual
    fecha_actualizacion      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (jugador_id, competicion, tipo_fila)
);

CREATE INDEX idx_carrera_jugador ON estadisticas_carrera(jugador_id);

-- ============================================================
-- DIARIO DE LESIONES
-- ============================================================

CREATE TABLE lesiones (
    id                            INTEGER PRIMARY KEY,
    jugador_id                    INTEGER NOT NULL REFERENCES jugadores(id) ON DELETE CASCADE,
    fecha_inicio                  DATE NOT NULL,
    fecha_fin_estimada            DATE,
    fecha_fin_real                DATE,
    tipo_lesion                   TEXT,             -- muscular, ligamentosa, ósea, articular... (texto libre)
    zona_corporal                 TEXT,             -- rodilla, tobillo, hombro... (texto libre)
    gravedad_id                   INTEGER REFERENCES grados_gravedad(id),
    diagnostico                   TEXT,
    tratamiento                   TEXT,
    partidos_perdidos_estimados   INTEGER,
    lesion_previa_id              INTEGER REFERENCES lesiones(id),   -- para marcar recaídas
    estado_id                     INTEGER NOT NULL DEFAULT 1 REFERENCES estados_lesion(id), -- 1 = En tratamiento
    fuente_id                     INTEGER NOT NULL DEFAULT 1 REFERENCES fuentes(id), -- 1 = Manual
    url_fuente                    TEXT,
    fiabilidad_id                 INTEGER NOT NULL DEFAULT 1 REFERENCES niveles_fiabilidad(id), -- 1 = Confirmado
    notas                         TEXT,
    fecha_registro                TEXT NOT NULL DEFAULT (datetime('now')),
    fecha_actualizacion           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_lesiones_jugador ON lesiones(jugador_id);

-- ============================================================
-- DATOS ECONÓMICOS
-- ============================================================

CREATE TABLE datos_economicos (
    id                     INTEGER PRIMARY KEY,
    jugador_id             INTEGER NOT NULL REFERENCES jugadores(id) ON DELETE CASCADE,
    equipo_id              INTEGER REFERENCES equipos(id),
    temporada              TEXT NOT NULL,
    tipo_contrato_id       INTEGER REFERENCES tipos_contrato(id),
    salario_estimado       REAL,
    moneda                 TEXT DEFAULT 'EUR',
    fecha_inicio_contrato  DATE,
    fecha_fin_contrato     DATE,
    clausula_rescision     REAL,
    agente_representante   TEXT,
    fuente_id              INTEGER NOT NULL DEFAULT 1 REFERENCES fuentes(id), -- 1 = Manual
    fiabilidad_id          INTEGER NOT NULL DEFAULT 2 REFERENCES niveles_fiabilidad(id), -- 2 = Estimado
    url_fuente             TEXT,
    notas                  TEXT,
    fecha_registro         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_economicos_jugador ON datos_economicos(jugador_id);

-- ============================================================
-- VALOR DE MERCADO (serie temporal, separada del salario)
-- ============================================================

CREATE TABLE valor_mercado (
    id               INTEGER PRIMARY KEY,
    jugador_id       INTEGER NOT NULL REFERENCES jugadores(id) ON DELETE CASCADE,
    fecha            DATE NOT NULL,
    valor_estimado   REAL NOT NULL,
    moneda           TEXT DEFAULT 'EUR',
    fuente           TEXT,
    notas            TEXT
);

CREATE INDEX idx_valor_mercado_jugador ON valor_mercado(jugador_id);

-- ============================================================
-- HITOS DE CARRERA / PALMARÉS
-- ============================================================

CREATE TABLE hitos_carrera (
    id             INTEGER PRIMARY KEY,
    jugador_id     INTEGER NOT NULL REFERENCES jugadores(id) ON DELETE CASCADE,
    temporada      TEXT,
    tipo           TEXT,            -- MVP, campeón, all-star, selección nacional...
    competicion    TEXT,
    descripcion    TEXT,
    fecha          DATE
);

CREATE INDEX idx_hitos_jugador ON hitos_carrera(jugador_id);
