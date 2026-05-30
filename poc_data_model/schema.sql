-- ============================================================================
-- Modelo de datos para el feedback del asistente conversacional SAGE-EVA.
-- POC en SQLite. Migrable a Postgres cambiando 4 tipos (TEXT→UUID,
-- TEXT→TIMESTAMPTZ, TEXT→JSONB, BLOB→vector(N)).
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------------
-- 1) CATÁLOGO DE CATEGORÍAS
-- Pocas filas, muy estables. Se separa para poder activar/desactivar
-- categorías sin tocar el código y para poder validar por FK.
-- ----------------------------------------------------------------------------
CREATE TABLE feedback_categories (
    slug         TEXT PRIMARY KEY,         -- 'ceremonia', 'organización', ...
    label        TEXT NOT NULL,            -- nombre legible
    description  TEXT,
    active       INTEGER NOT NULL DEFAULT 1   -- 1=visible, 0=archivada
);

-- ----------------------------------------------------------------------------
-- 2) SESIONES
-- Una sesión = una conversación. Hoy sage-agent guarda esto solo en memoria;
-- el modelo lo persiste con identidad estable (UUID) para poder analizarlo.
-- ----------------------------------------------------------------------------
CREATE TABLE sessions (
    id              TEXT PRIMARY KEY,                 -- UUID string
    started_at      TEXT NOT NULL,                    -- ISO8601 UTC
    ended_at        TEXT,                             -- NULL = en curso
    event_id        TEXT NOT NULL DEFAULT 'diplomas-ahk-2026',
    client_metadata TEXT                              -- JSON: user-agent, locale, etc.
);
CREATE INDEX idx_sessions_event_started ON sessions(event_id, started_at);

-- ----------------------------------------------------------------------------
-- 3) MENSAJES
-- Cada turno (del usuario o del asistente) es una fila con identidad estable.
-- Esto es lo que sage-agent NO tiene hoy y es lo que habilita "feedback sobre
-- una respuesta específica" — el message_id es el ancla.
-- ----------------------------------------------------------------------------
CREATE TABLE messages (
    id                 TEXT PRIMARY KEY,
    session_id         TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role               TEXT NOT NULL
                       CHECK (role IN ('user', 'assistant', 'system')),
    content            TEXT NOT NULL,
    created_at         TEXT NOT NULL,
    turn_index         INTEGER NOT NULL,              -- 1, 2, 3... por sesión
    parent_message_id  TEXT REFERENCES messages(id),  -- respuesta → mensaje que la motivó
    model_name         TEXT,                          -- 'llama3.2:3b' (NULL si role=user)
    token_count        INTEGER,
    latency_ms         INTEGER,
    UNIQUE (session_id, turn_index, role)
);
CREATE INDEX idx_messages_session   ON messages(session_id, created_at);
CREATE INDEX idx_messages_assistant ON messages(created_at) WHERE role = 'assistant';

-- ----------------------------------------------------------------------------
-- 4) FEEDBACK
-- Cada fila es una evaluación de UN mensaje. Un mismo mensaje puede tener
-- MÚLTIPLES feedbacks (uno auto_heuristic, uno auto_nlp, uno user_explicit,
-- etc.) sin pisarse. Eso permite A/B entre clasificadores y conservar
-- histórico cuando se reclasifica.
-- ----------------------------------------------------------------------------
CREATE TABLE feedback (
    id                  TEXT PRIMARY KEY,
    message_id          TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    session_id          TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,

    source              TEXT NOT NULL
                        CHECK (source IN (
                            'auto_heuristic',   -- detector keyword (feedback.py original)
                            'auto_nlp',         -- clasificador semántico futuro
                            'user_explicit',    -- thumbs/rating del invitado
                            'ia_team_manual'    -- corrección humana
                        )),
    classifier_version  TEXT NOT NULL,         -- 'keyword-v1', 'embeddings-v2', ...

    sentiment_label     TEXT
                        CHECK (sentiment_label IN
                              ('positive', 'negative', 'neutral', 'mixed')),
    sentiment_score     REAL CHECK (sentiment_score BETWEEN -1.0 AND 1.0),

    category            TEXT REFERENCES feedback_categories(slug),
    subcategory         TEXT,

    rating              INTEGER CHECK (rating BETWEEN 1 AND 5),
    thumbs              TEXT CHECK (thumbs IN ('up', 'down')),
    comment             TEXT,

    raw_signal          TEXT NOT NULL,         -- texto crudo que originó el feedback
    confidence          REAL CHECK (confidence BETWEEN 0 AND 1),

    created_at          TEXT NOT NULL,
    processed_at        TEXT,                  -- NULL hasta que el clasificador async termine
    metadata            TEXT                   -- JSON libre
);
CREATE INDEX idx_feedback_message       ON feedback(message_id);
CREATE INDEX idx_feedback_session       ON feedback(session_id, created_at);
CREATE INDEX idx_feedback_sentiment     ON feedback(sentiment_label, created_at);
CREATE INDEX idx_feedback_category      ON feedback(category, created_at);
CREATE INDEX idx_feedback_source_ver    ON feedback(source, classifier_version);

-- ----------------------------------------------------------------------------
-- 5) EMBEDDINGS (futuro NLP)
-- Tabla aparte porque los vectores son pesados y la mayoría de los queries
-- analíticos NO los necesitan. Mantener separados acelera todo.
-- En SQLite el vector se guarda como BLOB; en Postgres sería vector(384)
-- usando pgvector.
-- ----------------------------------------------------------------------------
CREATE TABLE feedback_embeddings (
    feedback_id  TEXT PRIMARY KEY REFERENCES feedback(id) ON DELETE CASCADE,
    model_name   TEXT NOT NULL,                -- ej. 'paraphrase-multilingual-MiniLM'
    dimensions   INTEGER NOT NULL,             -- 384, 768, etc.
    vector       BLOB NOT NULL,                -- representación binaria
    created_at   TEXT NOT NULL
);

-- ----------------------------------------------------------------------------
-- SEED del catálogo (datos de referencia, no operacionales)
-- ----------------------------------------------------------------------------
INSERT INTO feedback_categories (slug, label, description) VALUES
    ('ceremonia',    'Ceremonia',     'Acto: diplomas, discursos, palabras de autoridades'),
    ('organización', 'Organización',  'Logística, puntualidad, orden, esperas'),
    ('recepción',    'Recepción',     'Llegada, entrada, acreditación, bienvenida'),
    ('catering',     'Catering',      'Comida, bebida, buffet, networking'),
    ('contenido',    'Contenido',     'Calidad/exactitud de la información que dio EVA'),
    ('agente',       'Agente',        'Experiencia conversacional con EVA'),
    ('general',      'General',       'No encaja en las anteriores');
