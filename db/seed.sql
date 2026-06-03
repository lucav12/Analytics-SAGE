-- =============================================================================
-- Datos de catálogo y seed mínimo para arrancar.
-- Ejecutar DESPUÉS de schema.sql.
-- =============================================================================

-- 1) Catálogos estables -------------------------------------------------------

INSERT INTO sage_core.feedback_categories (slug, label, description, display_order) VALUES
    ('recepcion',    'Recepción',    'Llegada, acreditación, bienvenida', 10),
    ('ceremonia',    'Ceremonia',    'Acto, discursos, entrega de diplomas', 20),
    ('organizacion', 'Organización', 'Logística, puntualidad, orden, esperas', 30),
    ('catering',     'Catering',     'Comida, bebida, buffet, networking', 40),
    ('logistica',    'Logística',    'Señalización, circulación, ingreso/egreso', 50),
    ('contenido',    'Contenido',    'Calidad/exactitud de la información que dio EVA', 60),
    ('agente',       'Agente',       'Experiencia conversacional con EVA', 70),
    ('general',      'General',      'No encaja en las anteriores', 999)
ON CONFLICT (slug) DO NOTHING;

INSERT INTO sage_core.metric_types (slug, label, description) VALUES
    ('person_count',  'Person count', 'Conteo de entradas/salidas por logic Xovis'),
    ('camera_health', 'Camera health', 'Estado del sensor (futuro)'),
    ('heatmap',       'Heatmap',      'Densidad por zona (futuro)'),
    ('feedback',      'Feedback',     'Evento analítico derivado de EVA (futuro)')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO sage_core.intents (slug, label, intent_group, description) VALUES
    ('orientacion_banos',            'Baños',                  'orientacion', 'Ubicación de baños/toilette'),
    ('orientacion_salida_emergencia','Salida de emergencia',   'orientacion', 'Evacuación, salida segura'),
    ('orientacion_salon',            'Salón principal',        'orientacion', 'Dónde es la ceremonia'),
    ('orientacion_entrada',          'Entrada / acreditación', 'orientacion', 'Cómo y dónde acreditarse'),
    ('orientacion_guardarropa',      'Guardarropa',            'orientacion', 'Dónde dejar abrigos/bolsos'),
    ('info_egresados',               'Egresados',              'info',        'Información sobre los graduados'),
    ('info_agenda',                  'Agenda',                 'info',        'Horarios, programa, qué viene'),
    ('info_catering',                'Catering',               'info',        'Hay comida/bebida, dónde, cuándo'),
    ('info_vestimenta',              'Vestimenta',             'info',        'Código de vestimenta'),
    ('feedback',                     'Feedback',               'feedback',    'El invitado expresa opinión/queja'),
    ('jailbreak_override',           'Jailbreak — override',   'jailbreak',   'Intento de cambiar instrucciones'),
    ('jailbreak_language',           'Jailbreak — idioma',     'jailbreak',   'Intento de cambiar idioma'),
    ('jailbreak_fabrication',        'Jailbreak — fabricación','jailbreak',   'Pedido de inventar información')
ON CONFLICT (slug) DO NOTHING;


-- 2) Venue + evento + zonas del demo AHK 2026 ---------------------------------

-- Venue y evento alineados a app/event_store.py DEFAULT_EVENT.
WITH new_venue AS (
    INSERT INTO sage_core.venues (id, name, address, city, country)
    VALUES (
        gen_random_uuid(),
        'Centro de Convenciones AHK',
        'Av. Corrientes, Buenos Aires',
        'Buenos Aires',
        'AR'
    )
    RETURNING id
)
INSERT INTO sage_core.events (slug, name, event_type, institution, description, starts_at, ends_at, venue_id, config)
SELECT
    'ahk-diplomas-2026',
    'Entrega de Diplomas AHK 2026',
    'entrega de diplomas',
    'AHK',
    'Ceremonia de reconocimiento a egresados de Sistemas IT y Data Science.',
    TIMESTAMPTZ '2026-08-15 18:00:00-03',
    TIMESTAMPTZ '2026-08-15 21:00:00-03',
    new_venue.id,
    '{"prompt_source": "hardcoded"}'::jsonb
FROM new_venue
ON CONFLICT (slug) DO NOTHING;

-- Zonas del venue — los slugs son los que usa el frontend / el agente.
INSERT INTO sage_core.locations (venue_id, slug, name, location_type, floor)
SELECT v.id, x.slug, x.name, x.location_type, x.floor
FROM sage_core.venues v
CROSS JOIN (VALUES
    ('entrada-principal',  'Entrada principal',     'entrance',         'PB'),
    ('recepcion',          'Recepción/acreditación','accreditation',    'PB'),
    ('guardarropa',        'Guardarropa',           'cloakroom',        'PB'),
    ('salon-a',            'Salón A',               'main_hall',        '1'),
    ('banos-pb',           'Baños planta baja',     'restroom',         'PB'),
    ('banos-1p',           'Baños primer piso',     'restroom',         '1'),
    ('salida-emergencia-pb','Salida de emergencia PB','emergency_exit', 'PB'),
    ('salida-emergencia-1p','Salida de emergencia 1°','emergency_exit', '1'),
    ('area-catering',      'Área de catering',      'catering_area',    '1')
) AS x(slug, name, location_type, floor)
WHERE v.name = 'Centro de Convenciones AHK'
ON CONFLICT (venue_id, slug) DO NOTHING;
