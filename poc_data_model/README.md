# POC — Modelo de datos para feedback de SAGE-EVA

Prueba de concepto ejecutable del modelo de datos propuesto para el feedback
del asistente conversacional EVA. Cinco tablas, SQLite local, datos de
demostración realistas, y queries analíticos que prueban el valor del modelo.

**No toca el repo público `sage-agent`**. Vive autónomamente en este repo.

## Archivos

| Archivo | Qué hace |
|---|---|
| `schema.sql` | DDL completo: las 5 tablas + restricciones + índices + seed del catálogo. Es la fuente de verdad del modelo. |
| `build_db.py` | Crea `sage_analytics.db` a partir de `schema.sql`. Soporta `--reset`. |
| `seed_demo.py` | Puebla la DB con 3 sesiones, 12 mensajes y 9 feedbacks de los 4 sources distintos, incluyendo coexistencia de clasificadores sobre el mismo mensaje. |
| `demo_queries.py` | Corre 6 queries analíticos representativos e imprime los resultados. |
| `Modelo_de_Datos.docx` | Explicación pedagógica completa del modelo, pensada para audiencia sin conocimiento previo. |

## Quick start

```powershell
cd poc_data_model
python build_db.py --reset
python seed_demo.py
python demo_queries.py
```

## Las 5 tablas (vista rápida)

```
sessions  ──1:N──  messages  ──1:N──  feedback  ──1:0..1──  feedback_embeddings
                                          │
                                          └── N:1 ── feedback_categories
```

- **sessions** — una conversación entera (UUID + timestamps + evento).
- **messages** — cada turno con identidad estable (UUID). Esto es lo que permite
  referirse a "esta respuesta de EVA" — el sistema actual no lo tiene.
- **feedback** — N por mensaje. Permite coexistencia de clasificadores
  (heurística v1 + NLP v2 + thumbs explícito) sin sobrescribir histórico.
- **feedback_categories** — catálogo de 7 categorías, editable sin tocar código.
- **feedback_embeddings** — tabla aparte para vectores (futuro NLP). Tabla
  separada porque los vectores son grandes y la mayoría de los queries no los
  necesitan.

## Lo que la POC demuestra

El query #3 de `demo_queries.py` muestra el caso más representativo:

```
heuristic_v1 | nlp_v2    | verdict
-------------|-----------|--------
positive     | positive  | agree
positive     | mixed     | DISAGREE
neutral      | negative  | DISAGREE
```

Sobre el mismo `message_id`, la heurística vieja (`keyword-v1`) y un
clasificador NLP simulado (`embeddings-v2`) producen etiquetas distintas
en 2 de 3 casos. El modelo permite ver ese desacuerdo objetivamente y
decidir cuándo apagar la heurística.

## Migración a Postgres (cuando aplique)

Los cambios son mecánicos:

| SQLite | Postgres |
|---|---|
| `TEXT` (para UUID) | `UUID` con `DEFAULT gen_random_uuid()` |
| `TEXT` (para fechas ISO) | `TIMESTAMPTZ` |
| `TEXT` (para JSON) | `JSONB` |
| `BLOB` (para vectores) | `vector(N)` con extensión `pgvector` |
| `INTEGER` boolean (0/1) | `BOOLEAN` |

Los nombres de tablas, columnas, FKs e índices quedan iguales. El driver
pasaría de `sqlite3` a `psycopg`/`asyncpg`.

## Para profundizar

Leer `Modelo_de_Datos.docx` — explica desde cero qué es un modelo de datos,
los conceptos previos necesarios (PK, FK, cardinalidad, etc.), cada entidad
con justificación, las decisiones de diseño y un glosario para presentación.
