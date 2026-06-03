-- =============================================================================
-- SAGE Analytics — Modelo de datos integrado (PostgreSQL)
-- =============================================================================
-- Objetivo: integrar en un único almacén los dos productores de datos del
-- sistema SAGE:
--
--   1. sage-agent / Analytics-SAGE (EVA): conversaciones, feedback y métricas
--      derivadas del análisis de los mensajes.
--   2. sage-analytics-api: eventos crudos de cámaras Xovis y métricas
--      normalizadas tipo person_count.
--
-- El núcleo (eventos, venues, zonas, catálogos) está compartido para poder
-- cruzar feedback con tráfico físico ("¿el bajón de happiness coincidió con
-- el pico de aforo en la entrada?") y para que cualquier dashboard pueda
-- unir las dos fuentes en una sola query.
--
-- Convenciones:
--   - UUID v4 como PK en todas las tablas operacionales.
--   - TIMESTAMPTZ siempre — nada de timestamps naive.
--   - JSONB para payloads flexibles (Xovis raw, metadata libre).
--   - pgvector para embeddings de feedback (NLP a futuro).
--   - Tres schemas: sage_core, sage_agent, sage_analytics. Las VIEWs de
--     análisis cross-fuente viven en sage_views.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "vector";     -- pgvector — opcional pero recomendado

CREATE SCHEMA IF NOT EXISTS sage_core;
CREATE SCHEMA IF NOT EXISTS sage_agent;
CREATE SCHEMA IF NOT EXISTS sage_analytics;
CREATE SCHEMA IF NOT EXISTS sage_views;

SET search_path TO sage_core, sage_agent, sage_analytics, sage_views, public;


-- =============================================================================
-- 1) sage_core — entidades compartidas
-- =============================================================================
-- Estas tablas son el "punto de unión" entre EVA y los sensores. Todo
-- mensaje, feedback y métrica cae bajo un (event_id, location_id) que se
-- resuelve acá.
-- -----------------------------------------------------------------------------

CREATE TABLE sage_core.events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                TEXT NOT NULL UNIQUE,                  -- 'ahk-diplomas-2026'
    name                TEXT NOT NULL,                         -- 'Entrega de Diplomas AHK 2026'
    event_type          TEXT,                                  -- 'entrega de diplomas', 'congreso', ...
    institution         TEXT,                                  -- 'AHK'
    description         TEXT,
    starts_at           TIMESTAMPTZ NOT NULL,
    ends_at             TIMESTAMPTZ,
    timezone            TEXT NOT NULL DEFAULT 'America/Argentina/Buenos_Aires',
    venue_id            UUID,                                  -- FK definida más abajo
    config              JSONB NOT NULL DEFAULT '{}'::jsonb,    -- payload event_store.py
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE sage_core.venues (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,                         -- 'Centro de Convenciones AHK'
    address             TEXT,
    city                TEXT,
    country             TEXT,
    geo_lat             DOUBLE PRECISION,
    geo_lng             DOUBLE PRECISION,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE sage_core.events
    ADD CONSTRAINT events_venue_fk
    FOREIGN KEY (venue_id) REFERENCES sage_core.venues(id) ON DELETE SET NULL;

-- Locations = zonas dentro de un venue. Es la unidad de join entre
-- "qué cámara está mirando" y "qué dice EVA sobre esa zona".
CREATE TABLE sage_core.locations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    venue_id            UUID NOT NULL REFERENCES sage_core.venues(id) ON DELETE CASCADE,
    slug                TEXT NOT NULL,                         -- 'entrada-principal', 'salon-a'
    name                TEXT NOT NULL,                         -- 'Entrada principal'
    location_type       TEXT NOT NULL                          -- 'entrance', 'hall', 'restroom', ...
                        CHECK (location_type IN (
                            'entrance', 'accreditation', 'cloakroom', 'main_hall',
                            'restroom', 'emergency_exit', 'catering_area',
                            'networking_area', 'corridor', 'other'
                        )),
    floor               TEXT,                                  -- 'PB', '1', '2'
    capacity            INTEGER,                               -- aforo nominal
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (venue_id, slug)
);
CREATE INDEX locations_venue_idx ON sage_core.locations(venue_id);


-- Catálogo de categorías de feedback (estable, pocas filas, validable por FK).
CREATE TABLE sage_core.feedback_categories (
    slug                TEXT PRIMARY KEY,                      -- 'ceremonia', 'organizacion', ...
    label               TEXT NOT NULL,
    description         TEXT,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    display_order       SMALLINT NOT NULL DEFAULT 100
);

-- Catálogo de tipos de métrica producibles por sage-analytics-api.
CREATE TABLE sage_core.metric_types (
    slug                TEXT PRIMARY KEY,                      -- 'person_count', 'camera_health', ...
    label               TEXT NOT NULL,
    description         TEXT,
    schema_version      TEXT NOT NULL DEFAULT '0.1.0'
);

-- Catálogo de intents que reconoce EVA — sirve para que el dashboard
-- valide y enriquezca cualquier intent log con metadata estable.
CREATE TABLE sage_core.intents (
    slug                TEXT PRIMARY KEY,                      -- 'orientacion_banos', 'feedback', ...
    label               TEXT NOT NULL,
    intent_group        TEXT NOT NULL                          -- 'orientacion', 'info', 'feedback', ...
                        CHECK (intent_group IN (
                            'orientacion', 'info', 'feedback', 'jailbreak', 'other'
                        )),
    description         TEXT
);


-- =============================================================================
-- 2) sage_agent — datos producidos por EVA (sage-agent / Analytics-SAGE)
-- =============================================================================
-- Reemplaza la persistencia actual en archivos JSON (feedback_log.json,
-- current_event.json) con un modelo relacional que permite analizar
-- conversaciones turn-by-turn y feedback multi-categoría con scores.
-- -----------------------------------------------------------------------------

-- Cada sesión = una conversación con EVA. Hoy sage-agent guarda esto solo
-- en memoria (self.session_id en agent.py); acá pasa a tener identidad
-- estable y arrancar/cerrar real.
CREATE TABLE sage_agent.sessions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id            UUID NOT NULL REFERENCES sage_core.events(id) ON DELETE CASCADE,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at            TIMESTAMPTZ,
    prompt_source       TEXT NOT NULL DEFAULT 'hardcoded'      -- alineado a PROMPT_SOURCE
                        CHECK (prompt_source IN ('hardcoded', 'dynamic')),
    model_name          TEXT,                                  -- 'llama3.2:3b', etc.
    client_metadata     JSONB NOT NULL DEFAULT '{}'::jsonb     -- user-agent, locale, device
);
CREATE INDEX sessions_event_idx ON sage_agent.sessions(event_id, started_at DESC);


-- Cada turno (user o assistant) como fila propia. Esto es lo que
-- sage-agent NO tiene hoy y es el ancla que habilita el join feedback ↔
-- respuesta específica que motivó el feedback.
CREATE TABLE sage_agent.messages (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          UUID NOT NULL REFERENCES sage_agent.sessions(id) ON DELETE CASCADE,
    role                TEXT NOT NULL
                        CHECK (role IN ('user', 'assistant', 'system')),
    content             TEXT NOT NULL,
    turn_index          INTEGER NOT NULL,                      -- 1, 2, 3 ... por sesión
    parent_message_id   UUID REFERENCES sage_agent.messages(id),
    intent_slug         TEXT REFERENCES sage_core.intents(slug),
    intent_score        REAL CHECK (intent_score BETWEEN 0 AND 1),
    token_count         INTEGER,
    latency_ms          INTEGER,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (session_id, turn_index, role)
);
CREATE INDEX messages_session_idx   ON sage_agent.messages(session_id, created_at);
CREATE INDEX messages_intent_idx    ON sage_agent.messages(intent_slug, created_at);
CREATE INDEX messages_assistant_idx ON sage_agent.messages(created_at)
    WHERE role = 'assistant';


-- Cada fila de feedback es UNA evaluación de un mensaje. Un mensaje puede
-- recibir MÚLTIPLES feedbacks (auto_nlp + user_explicit + ia_team_manual)
-- sin pisarse — eso habilita A/B entre clasificadores y conservar histórico
-- cuando se reclasifica con un modelo nuevo.
CREATE TABLE sage_agent.feedback (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          UUID NOT NULL REFERENCES sage_agent.sessions(id) ON DELETE CASCADE,
    message_id          UUID NOT NULL REFERENCES sage_agent.messages(id) ON DELETE CASCADE,

    source              TEXT NOT NULL
                        CHECK (source IN (
                            'auto_intent',       -- match del intent matcher principal
                            'auto_detector',     -- FeedbackDetector binario
                            'user_explicit',     -- thumbs/rating del invitado
                            'ia_team_manual'     -- corrección humana
                        )),
    classifier_version  TEXT NOT NULL,                         -- 'embeddings-v1', 'detector-v1', ...

    -- Categoría principal + multi-categoría con scores (multi-etiqueta).
    -- Mantiene FK al catálogo para evitar typos en el nombre de la categoría.
    primary_category    TEXT REFERENCES sage_core.feedback_categories(slug),

    -- Scores propios de Analytics-SAGE (el aporte sobre sage-agent base).
    happiness_score          SMALLINT CHECK (happiness_score BETWEEN 0 AND 10),
    net_promoter_score       SMALLINT CHECK (net_promoter_score BETWEEN 0 AND 10),
    return_likelihood_score  SMALLINT CHECK (return_likelihood_score BETWEEN 0 AND 10),
    sentiment_label          TEXT
                             CHECK (sentiment_label IN
                                ('positive', 'negative', 'neutral', 'mixed')),

    raw_signal          TEXT NOT NULL,                         -- texto original del invitado
    confidence          REAL CHECK (confidence BETWEEN 0 AND 1),
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at        TIMESTAMPTZ
);
CREATE INDEX feedback_session_idx      ON sage_agent.feedback(session_id, created_at);
CREATE INDEX feedback_message_idx      ON sage_agent.feedback(message_id);
CREATE INDEX feedback_category_idx     ON sage_agent.feedback(primary_category, created_at);
CREATE INDEX feedback_source_idx       ON sage_agent.feedback(source, classifier_version);
CREATE INDEX feedback_happiness_idx    ON sage_agent.feedback(happiness_score)
    WHERE happiness_score IS NOT NULL;


-- Scores por categoría (multi-etiqueta). Un feedback puede mencionar
-- catering Y organización con scores distintos — los conservamos a todos.
CREATE TABLE sage_agent.feedback_category_scores (
    feedback_id         UUID NOT NULL REFERENCES sage_agent.feedback(id) ON DELETE CASCADE,
    category_slug       TEXT NOT NULL REFERENCES sage_core.feedback_categories(slug),
    score               REAL NOT NULL CHECK (score BETWEEN 0 AND 1),
    rank                SMALLINT NOT NULL,                     -- 1 = mejor match
    PRIMARY KEY (feedback_id, category_slug)
);
CREATE INDEX feedback_cat_scores_cat_idx ON sage_agent.feedback_category_scores(category_slug, score DESC);


-- Embeddings del texto del feedback (futuro NLP / clustering).
-- Aparte de la tabla principal porque los vectores son pesados y la mayoría
-- de las queries analíticas no los necesitan.
CREATE TABLE sage_agent.feedback_embeddings (
    feedback_id         UUID PRIMARY KEY REFERENCES sage_agent.feedback(id) ON DELETE CASCADE,
    model_name          TEXT NOT NULL,                         -- 'nomic-embed-text'
    dimensions          INTEGER NOT NULL,                      -- 768 (nomic), 384, etc.
    embedding           vector(768),                           -- pgvector — ajustar dim si se cambia
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Índice ivfflat para nearest-neighbor sobre embeddings (NLP / clustering).
CREATE INDEX feedback_embeddings_ann_idx
    ON sage_agent.feedback_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);


-- Log de jailbreaks bloqueados — útil para seguridad y para mejorar el
-- detector. Hoy esa info se pierde en stdout.
CREATE TABLE sage_agent.jailbreak_attempts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          UUID NOT NULL REFERENCES sage_agent.sessions(id) ON DELETE CASCADE,
    jailbreak_type      TEXT NOT NULL                          -- 'override', 'language', 'fabrication'
                        CHECK (jailbreak_type IN ('override', 'language', 'fabrication')),
    raw_message         TEXT NOT NULL,
    response_sent       TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX jailbreak_session_idx ON sage_agent.jailbreak_attempts(session_id);


-- =============================================================================
-- 3) sage_analytics — datos producidos por sage-analytics-api
-- =============================================================================
-- Reemplaza la persistencia actual en disco (`data/raw-events/*.json`) con
-- un modelo relacional. Mantiene el payload Xovis original en JSONB para
-- trazabilidad y agrega columnas normalizadas para queries rápidas.
-- -----------------------------------------------------------------------------

CREATE TABLE sage_analytics.devices (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_slug         TEXT NOT NULL UNIQUE,                  -- 'xovis-ahk-pb'
    vendor              TEXT NOT NULL DEFAULT 'xovis',
    model               TEXT,                                  -- 'PC2SE'
    sensor_serial       TEXT,                                  -- 'ANON-XOVIS-DEVICE-01'
    sensor_type         TEXT,                                  -- 'SINGLE_SENSOR', ...
    location_id         UUID REFERENCES sage_core.locations(id) ON DELETE SET NULL,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    registered_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX devices_location_idx ON sage_analytics.devices(location_id);


-- Histórico de asignación device → location. Si una cámara cambia de zona
-- a mitad del evento, el histórico mantiene la verdad por ventana de tiempo.
CREATE TABLE sage_analytics.device_locations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id           UUID NOT NULL REFERENCES sage_analytics.devices(id) ON DELETE CASCADE,
    location_id         UUID NOT NULL REFERENCES sage_core.locations(id) ON DELETE CASCADE,
    valid_from          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to            TIMESTAMPTZ
);
CREATE INDEX device_locations_device_idx
    ON sage_analytics.device_locations(device_id, valid_from DESC);


-- Payload Xovis raw — equivalente a XovisRawEvent del sage-analytics-api.
-- Se preserva tal cual llegó para poder reprocesar con un parser nuevo si
-- aparece un bug en la normalización.
CREATE TABLE sage_analytics.xovis_raw_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id           UUID REFERENCES sage_analytics.devices(id) ON DELETE SET NULL,
    device_slug         TEXT NOT NULL,                         -- por si llega antes de registrar device
    source              TEXT NOT NULL DEFAULT 'xovis',
    schema_version      TEXT NOT NULL DEFAULT '0.1.0',
    received_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload             JSONB NOT NULL,                        -- contenido raw del POST Xovis
    storage_relative_path TEXT                                 -- /data/raw-events/.../file.json — legacy
);
CREATE INDEX xovis_raw_received_idx ON sage_analytics.xovis_raw_events(received_at DESC);
CREATE INDEX xovis_raw_device_idx   ON sage_analytics.xovis_raw_events(device_id, received_at DESC);
CREATE INDEX xovis_raw_payload_gin  ON sage_analytics.xovis_raw_events USING GIN (payload jsonb_path_ops);


-- Métricas normalizadas — equivalente a NormalizedMetric del API. Una fila
-- por (logic, record) parseado del payload raw, o por payload-level cuando
-- no hay logics_data.
CREATE TABLE sage_analytics.normalized_metrics (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_event_id        UUID REFERENCES sage_analytics.xovis_raw_events(id) ON DELETE CASCADE,
    device_id           UUID REFERENCES sage_analytics.devices(id) ON DELETE SET NULL,
    event_id            UUID REFERENCES sage_core.events(id) ON DELETE SET NULL,
    location_id         UUID REFERENCES sage_core.locations(id) ON DELETE SET NULL,
    metric_type         TEXT NOT NULL REFERENCES sage_core.metric_types(slug),
    source              TEXT NOT NULL DEFAULT 'xovis',
    schema_version      TEXT NOT NULL DEFAULT '0.1.0',
    timestamp           TIMESTAMPTZ NOT NULL,                  -- cierre de ventana (= timestamp_to si existe)
    timestamp_from      TIMESTAMPTZ,
    timestamp_to        TIMESTAMPTZ,
    received_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    data                JSONB NOT NULL DEFAULT '{}'::jsonb     -- payload normalizado (PersonCountMetricData u otros)
);
CREATE INDEX metrics_timestamp_idx    ON sage_analytics.normalized_metrics(timestamp DESC);
CREATE INDEX metrics_event_time_idx   ON sage_analytics.normalized_metrics(event_id, timestamp DESC);
CREATE INDEX metrics_location_time_idx ON sage_analytics.normalized_metrics(location_id, timestamp DESC);
CREATE INDEX metrics_device_time_idx  ON sage_analytics.normalized_metrics(device_id, timestamp DESC);
CREATE INDEX metrics_type_time_idx    ON sage_analytics.normalized_metrics(metric_type, timestamp DESC);


-- Detalle person_count proyectado en columnas para queries más rápidas.
-- Es una "vista columnar" del JSONB de normalized_metrics.data, no una
-- segunda fuente de verdad — se llena en el mismo insert.
CREATE TABLE sage_analytics.person_count_records (
    metric_id           UUID PRIMARY KEY REFERENCES sage_analytics.normalized_metrics(id) ON DELETE CASCADE,
    forward_count       INTEGER NOT NULL CHECK (forward_count >= 0),
    backward_count      INTEGER NOT NULL CHECK (backward_count >= 0),
    total_count         INTEGER NOT NULL CHECK (total_count >= 0),
    samples             INTEGER,
    samples_expected    INTEGER,
    -- Metadata Xovis Logic Push (todo opcional — vacía cuando es payload genérico).
    package_version     TEXT,
    package_id          INTEGER,
    agent_id            INTEGER,
    logic_id            INTEGER,
    logic_name          TEXT,
    logic_info          TEXT,
    geometry_id         INTEGER,
    geometry_type       TEXT,
    geometry_name       TEXT
);
CREATE INDEX pcr_logic_idx ON sage_analytics.person_count_records(logic_id);


-- =============================================================================
-- 4) sage_views — análisis cross-fuente (feedback ↔ tráfico físico)
-- =============================================================================
-- Materializaciones livianas. La idea: que el dashboard pueda graficar de
-- una sola query "happiness promedio vs. aforo de la zona" sin hacer joins
-- pesados ad-hoc cada vez.
-- -----------------------------------------------------------------------------

-- Pulso por minuto del evento: combina person_count por minuto con
-- promedios de scores del feedback recibido en ese mismo minuto.
CREATE MATERIALIZED VIEW sage_views.event_pulse_minute AS
WITH
flow AS (
    SELECT
        nm.event_id,
        nm.location_id,
        date_trunc('minute', nm.timestamp) AS minute,
        SUM(COALESCE(pcr.forward_count, 0))  AS ingress,
        SUM(COALESCE(pcr.backward_count, 0)) AS egress,
        SUM(COALESCE(pcr.total_count, 0))    AS total_count
    FROM sage_analytics.normalized_metrics nm
    LEFT JOIN sage_analytics.person_count_records pcr
        ON pcr.metric_id = nm.id
    WHERE nm.metric_type = 'person_count'
    GROUP BY nm.event_id, nm.location_id, date_trunc('minute', nm.timestamp)
),
mood AS (
    SELECT
        s.event_id,
        NULL::uuid                          AS location_id,    -- feedback no tiene zona aún
        date_trunc('minute', f.created_at)  AS minute,
        COUNT(*)                            AS feedback_count,
        AVG(f.happiness_score)::numeric(4,2)         AS avg_happiness,
        AVG(f.net_promoter_score)::numeric(4,2)      AS avg_nps,
        AVG(f.return_likelihood_score)::numeric(4,2) AS avg_return_likelihood
    FROM sage_agent.feedback f
    JOIN sage_agent.sessions s ON s.id = f.session_id
    GROUP BY s.event_id, date_trunc('minute', f.created_at)
)
SELECT
    COALESCE(flow.event_id, mood.event_id)       AS event_id,
    COALESCE(flow.minute, mood.minute)           AS minute,
    flow.location_id,
    flow.ingress,
    flow.egress,
    flow.total_count,
    mood.feedback_count,
    mood.avg_happiness,
    mood.avg_nps,
    mood.avg_return_likelihood
FROM flow
FULL OUTER JOIN mood
    ON flow.event_id = mood.event_id
   AND flow.minute   = mood.minute;

CREATE INDEX event_pulse_minute_idx
    ON sage_views.event_pulse_minute(event_id, minute);


-- Categorías más mencionadas por hora — para el dashboard de PMs:
-- "¿qué se está quejando la gente ahora mismo?".
CREATE MATERIALIZED VIEW sage_views.feedback_category_hourly AS
SELECT
    s.event_id,
    date_trunc('hour', f.created_at)        AS hour,
    fcs.category_slug,
    COUNT(*)                                AS mentions,
    AVG(fcs.score)::numeric(4,3)            AS avg_score,
    AVG(f.happiness_score)::numeric(4,2)    AS avg_happiness_for_category
FROM sage_agent.feedback f
JOIN sage_agent.sessions s              ON s.id = f.session_id
JOIN sage_agent.feedback_category_scores fcs ON fcs.feedback_id = f.id
GROUP BY s.event_id, date_trunc('hour', f.created_at), fcs.category_slug;

CREATE INDEX feedback_cat_hourly_idx
    ON sage_views.feedback_category_hourly(event_id, hour, category_slug);


-- Distribución de intents por hora — útil para ver qué consultan los
-- invitados en tiempo real ("a las 19:00 todos preguntan por baños").
CREATE MATERIALIZED VIEW sage_views.intent_distribution_hourly AS
SELECT
    s.event_id,
    date_trunc('hour', m.created_at)    AS hour,
    m.intent_slug,
    COUNT(*)                            AS matches,
    AVG(m.intent_score)::numeric(4,3)   AS avg_score
FROM sage_agent.messages m
JOIN sage_agent.sessions s ON s.id = m.session_id
WHERE m.role = 'user' AND m.intent_slug IS NOT NULL
GROUP BY s.event_id, date_trunc('hour', m.created_at), m.intent_slug;

CREATE INDEX intent_dist_hourly_idx
    ON sage_views.intent_distribution_hourly(event_id, hour, intent_slug);


-- =============================================================================
-- 5) Trigger de updated_at en events
-- =============================================================================
CREATE OR REPLACE FUNCTION sage_core._touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER events_touch_updated_at
    BEFORE UPDATE ON sage_core.events
    FOR EACH ROW EXECUTE FUNCTION sage_core._touch_updated_at();
