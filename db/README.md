# Modelo de datos — SAGE Analytics

Este directorio contiene el modelo de datos PostgreSQL que integra los dos
productores de datos del sistema SAGE:

- **Analytics-SAGE / sage-agent (EVA)** — conversaciones con el asistente y
  feedback de los invitados.
- **sage-analytics-api** — eventos crudos de cámaras Xovis PC2SE y métricas
  normalizadas (`person_count`).

La idea es tener un único almacén donde el feedback ("la fila era larguísima")
y el tráfico físico ("a las 19:02 entraron 87 personas por la puerta principal")
se puedan cruzar en una sola query.

## Archivos

| Archivo | Para qué |
|---|---|
| [`schema.sql`](schema.sql) | DDL completo: schemas, tablas, índices, vistas materializadas |
| [`seed.sql`](seed.sql) | Catálogos (categorías, intents, tipos de métrica) + evento demo AHK 2026 |
| [`sample_queries.sql`](sample_queries.sql) | Queries de ejemplo cross-fuente |
| [`migrations/0001_init.sql`](migrations/0001_init.sql) | Migración inicial — incluye `schema.sql` |

## Pre-requisitos

- PostgreSQL 14+ (usamos `gen_random_uuid()` y JSONB).
- Extensiones: `pgcrypto` (UUIDs) y `vector` (pgvector, para embeddings de
  feedback). Si no querés instalar pgvector, comentá esa extensión y la tabla
  `sage_agent.feedback_embeddings`.

## Aplicar el schema

```bash
createdb sage_analytics
psql sage_analytics -f db/schema.sql
psql sage_analytics -f db/seed.sql
```

## Schemas

```
sage_core       # entidades compartidas — events, venues, locations, catálogos
sage_agent      # datos producidos por EVA — sessions, messages, feedback
sage_analytics  # datos producidos por sage-analytics-api — devices, raw events, metrics
sage_views      # vistas materializadas para análisis cross-fuente
```

Ver [`../DOC.md`](../DOC.md) para la explicación detallada de cada tabla y
las decisiones de diseño.
