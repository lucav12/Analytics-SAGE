-- =============================================================================
-- Queries de ejemplo — cómo se usa el modelo integrado.
-- =============================================================================

-- 1) Top 5 categorías de feedback en lo que va del evento, con NPS promedio.
SELECT
    fc.label                         AS categoria,
    COUNT(*)                         AS feedbacks,
    AVG(f.happiness_score)::numeric(4,2)         AS happiness_promedio,
    AVG(f.net_promoter_score)::numeric(4,2)      AS nps_promedio,
    AVG(f.return_likelihood_score)::numeric(4,2) AS volveria_promedio
FROM sage_agent.feedback f
JOIN sage_agent.sessions s        ON s.id = f.session_id
JOIN sage_core.events e           ON e.id = s.event_id
JOIN sage_core.feedback_categories fc ON fc.slug = f.primary_category
WHERE e.slug = 'ahk-diplomas-2026'
GROUP BY fc.label
ORDER BY feedbacks DESC
LIMIT 5;


-- 2) ¿El bajón de happiness coincide con un pico de aforo en la entrada?
--    Aforo (ingress) por minuto en la entrada principal y feedback promedio.
SELECT
    minute,
    SUM(ingress)            AS ingreso_total,
    AVG(avg_happiness)::numeric(4,2) AS happiness_promedio
FROM sage_views.event_pulse_minute epm
JOIN sage_core.events e ON e.id = epm.event_id
LEFT JOIN sage_core.locations l ON l.id = epm.location_id
WHERE e.slug = 'ahk-diplomas-2026'
  AND (l.slug = 'entrada-principal' OR l.slug IS NULL)
GROUP BY minute
ORDER BY minute;


-- 3) Sesiones que dejaron feedback negativo (happiness < 4) — para revisión
--    cualitativa del equipo de UX.
SELECT
    s.id                AS session_id,
    s.started_at,
    m.content           AS mensaje_invitado,
    f.happiness_score,
    f.net_promoter_score,
    f.primary_category,
    array_agg(fcs.category_slug ORDER BY fcs.rank) AS categorias_top
FROM sage_agent.feedback f
JOIN sage_agent.sessions s ON s.id = f.session_id
JOIN sage_agent.messages m ON m.id = f.message_id
LEFT JOIN sage_agent.feedback_category_scores fcs ON fcs.feedback_id = f.id
WHERE f.happiness_score < 4
GROUP BY s.id, s.started_at, m.content, f.happiness_score, f.net_promoter_score, f.primary_category
ORDER BY s.started_at DESC
LIMIT 50;


-- 4) Aforo neto (ingress - egress) acumulado por zona, durante el evento.
SELECT
    l.name                    AS zona,
    SUM(pcr.forward_count)    AS entradas,
    SUM(pcr.backward_count)   AS salidas,
    SUM(pcr.forward_count - pcr.backward_count) AS neto_acumulado
FROM sage_analytics.normalized_metrics nm
JOIN sage_analytics.person_count_records pcr ON pcr.metric_id = nm.id
JOIN sage_core.locations l ON l.id = nm.location_id
JOIN sage_core.events e ON e.id = nm.event_id
WHERE e.slug = 'ahk-diplomas-2026'
  AND nm.metric_type = 'person_count'
GROUP BY l.name
ORDER BY neto_acumulado DESC;


-- 5) Vecinos semánticos de un feedback dado — útil para encontrar comentarios
--    similares y agrupar quejas recurrentes (requiere embeddings poblados).
WITH target AS (
    SELECT embedding
    FROM sage_agent.feedback_embeddings
    WHERE feedback_id = '00000000-0000-0000-0000-000000000000'  -- reemplazar
)
SELECT
    f.id,
    f.raw_signal,
    f.happiness_score,
    1 - (fe.embedding <=> target.embedding) AS similitud_coseno
FROM sage_agent.feedback_embeddings fe
JOIN sage_agent.feedback f ON f.id = fe.feedback_id
CROSS JOIN target
ORDER BY fe.embedding <=> target.embedding
LIMIT 10;


-- 6) Refresh de materialized views — correr periódicamente (cron, pgAgent).
REFRESH MATERIALIZED VIEW sage_views.event_pulse_minute;
REFRESH MATERIALIZED VIEW sage_views.feedback_category_hourly;
REFRESH MATERIALIZED VIEW sage_views.intent_distribution_hourly;
