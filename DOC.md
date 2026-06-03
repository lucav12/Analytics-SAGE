# Analytics-SAGE — Documentación técnica

Este documento explica, sin asumir contexto previo:

1. Qué era Analytics-SAGE antes de este trabajo y por qué había que tocarlo.
2. Cómo se sincronizó con el repo upstream `sage-agent`.
3. Qué aporta Analytics-SAGE por encima de `sage-agent` (clasificador de
   feedback enriquecido).
4. **El modelo de datos PostgreSQL integrado** — la parte central de este
   trabajo. Se explica tabla por tabla, qué problema resuelve cada una y
   cómo se conectan los dos lados del sistema.
5. Cómo desplegarlo y cómo extenderlo.

---

## 1. Punto de partida

Analytics-SAGE tenía dos ramas muy distintas:

- **`main`** — un POC inicial con un archivo monolítico `feedback_api.py` y
  un directorio `poc_data_model/` con un schema SQLite (no Postgres) y
  scripts para generar demos. Servía como prueba de concepto del modelo de
  datos, pero el código del agente conversacional era una versión muy
  vieja.
- **`feature/mike`** — un fork del repo upstream
  [`SAGE-AHK/sage-agent`](https://github.com/SAGE-AHK/sage-agent), tomado
  en algún punto cerca de los commits de _intent matching vectorial_ y
  _CORS/SSE/Stream_ (junio/julio 2025). Sobre esa base, Mike construyó un
  clasificador de feedback enriquecido (categorías + happiness/NPS/return).

Mientras tanto, `sage-agent` siguió evolucionando: dotenv, prompt
dinámico, persistencia del evento (`event_store.py`), prompt builder,
Piper TTS, `run.sh`, configuración por LAN, etc. Esos cambios nunca
llegaron a Analytics-SAGE.

Encima de esa deuda, faltaba la pieza que el POC original solo había
prototipado: un modelo de datos **real, en Postgres**, que además unificara
lo que produce EVA (conversaciones + feedback) con lo que produce
[`sage-analytics-api`](https://github.com/SAGE-AHK/sage-analytics-api)
(eventos Xovis + métricas de aforo).

Este branch (`feature/sync-and-data-model`) resuelve los tres problemas
en commits separados:

| Commit | Qué hace |
|---|---|
| `chore: sync con sage-agent main` | Alinea Analytics-SAGE al último estado upstream |
| `feat: clasificador enriquecido de feedback` | Re-aplica el aporte de Mike sobre la base actualizada |
| `feat: modelo de datos PostgreSQL integrado` | Schema + seed + queries + helper Python |
| `docs: integración + modelo de datos` | Este archivo |

---

## 2. Sincronización con `sage-agent` upstream

Analytics-SAGE no fue forkeado vía git (no comparte historial), sino que
en su momento se copió el código de `sage-agent` a mano. Por eso no es
posible un `git merge` directo: lo que se hizo es reemplazar el código
común por el de upstream y _re-aplicar_ encima los cambios propios.

### Lo que se trajo de `sage-agent` (commit 1)

- `app/main.py` — endpoints nuevos `/tts`, `/eventos/actual`, `/configure`,
  con warmup de Piper en background, `load_dotenv()` al arranque y
  selección de prompt entre `hardcoded` y `dynamic`.
- `app/agent.py` — Ollama configurable por variables de entorno
  (`OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_REQUEST_TIMEOUT`),
  `temperature=0.3`, `repeat_penalty=1.1`, warm-up en thread daemon.
- `app/prompts.py` — reglas mucho más estrictas ("si no tenés el dato,
  respondé SIEMPRE: …"), few-shot examples para casos de borde.
- `app/event_store.py` — persistencia del evento activo en JSON, con un
  `DEFAULT_EVENT` muy completo.
- `app/prompt_builder.py` — construye el system prompt desde el JSON
  estructurado del evento (modo `dynamic`).
- `run.sh`, `.env.example`, `.gitignore`, `GIT_WORKFLOW.md`.
- `requirements.txt` ahora incluye `python-dotenv`.

### Lo que se limpió

- `app/__pycache__/` versionado por error.
- `app/prompts.py.save` (artefacto del editor).
- `app/feedback_log.json` versionado con datos de prueba.

### Lo que se mantuvo de `feature/mike`

- `Dockerfile` — se mantuvo (`sage-agent` no tiene). Se modernizó para
  usar `apt-get` sin `recommends`, variables de entorno razonables y
  delegar el arranque en `run.sh`.

---

## 3. El aporte de Analytics-SAGE: clasificador de feedback enriquecido

Una vez sincronizada la base, se re-aplicó el aporte que diferencia a
Analytics-SAGE de `sage-agent`. Es lo que justifica el repo y es lo que
alimenta directamente el modelo de datos.

### `app/feedback.py` — multi-categoría + scores

`sage-agent` guarda el feedback como `{session_id, mensaje, respuesta,
categoria}`. Analytics-SAGE guarda además:

- **`categorias[]`** — todas las categorías que aplican al mensaje, no
  solo la primera. Un mensaje puede hablar de catering Y de organización a
  la vez.
- **`categorias_scores[]`** — el score de embedding por cada categoría
  matcheada. Es lo que permite comparar clasificadores en el tiempo
  (y elegir un threshold por categoría).
- **`happiness_score`** (0–10) — heurística por keywords con detección de
  negaciones. "No me gustó" no cuenta como positivo aunque contenga
  "gustó".
- **`net_promoter_score`** (0–10) — override por keywords de promoción
  ("lo recomiendo" → 9) o detracción ("no lo recomiendo" → 1); si no hay
  señal NPS, hereda de `happiness_score`.
- **`return_likelihood_score`** (0–10) — misma lógica para "quiero volver"
  / "no vuelvo".

Catálogo de categorías: `recepcion`, `ceremonia`, `organizacion`,
`catering`, `logistica` (más `general` como fallback).

### `app/embeddings.py` — `IntentMatcher` parametrizable + `FeedbackDetector`

- `IntentMatcher` ahora acepta `intents` y `thresholds` por constructor.
  Eso lo convierte en un clasificador genérico — `feedback.py` lo
  instancia con su propio catálogo de categorías y umbral propio (0.72)
  sin tocar el `IntentMatcher` principal del agente.
- Nuevo `match_all()` que devuelve todas las categorías por encima del
  umbral, ordenadas por score (multi-etiqueta).
- `FeedbackDetector` — clasificador binario _es feedback / no es
  feedback_, separado del `IntentMatcher`. Compara el mensaje contra un
  corpus de opiniones y otro de preguntas y se queda con el más cercano.
  Captura quejas experienciales que el intent matcher solo no detecta
  (_"esperé muchísimo para acreditarme"_).

### `app/agent.py` — detección de feedback en dos capas

```python
is_feedback = intent == "feedback"          # capa 1: intent matcher
if not is_feedback:
    is_feedback, _ = get_feedback_detector().is_feedback(user_message)  # capa 2
if is_feedback:
    save_feedback(self.session_id, user_message, assistant_message)
```

`save_feedback()` ya no recibe categoría hardcodeada — `feedback.py`
clasifica multi-etiqueta y calcula los scores.

---

## 4. El modelo de datos PostgreSQL integrado

**Esta es la parte central del trabajo.** Acá se explica cada decisión.

### 4.1 ¿Por qué un modelo nuevo?

Los dos sistemas que conviven hoy guardan datos así:

- **`sage-agent` / Analytics-SAGE** persiste feedback en
  `app/feedback_log.json` (un array append-only). Sesiones y mensajes
  solo viven en memoria.
- **`sage-analytics-api`** guarda los payloads Xovis raw en
  `data/raw-events/*.json` (o en `/tmp` en Render, que se borra). Las
  métricas normalizadas se calculan y se devuelven en el response — no
  se guardan en ningún lado.

Esto tiene dos problemas serios:

1. **Nada es queryable.** Para responder _"¿cuándo bajó el NPS y qué
   pasaba con el aforo en la entrada?"_ hay que parsear dos directorios
   de JSONs.
2. **Los dos sistemas no se hablan.** No hay ningún concepto compartido
   de "evento", "zona del venue" o "ventana de tiempo". El feedback dice
   "la fila era larguísima" y el sensor Xovis dice "entraron 87 personas
   a las 19:02" — pero nadie los junta.

El modelo en `db/schema.sql` resuelve ambos.

### 4.2 Diagrama conceptual

```
                         ┌──────────────────────────────────────────────┐
                         │                 sage_core                    │
                         │  ┌──────┐  ┌──────┐  ┌──────────┐            │
                         │  │events│←─│venues│←─│locations │            │
                         │  └──┬───┘  └──────┘  └────┬─────┘            │
                         │     │  ┌───────────────┐  │                  │
                         │     │  │ feedback_     │  │                  │
                         │     │  │ categories    │  │                  │
                         │     │  └───────┬───────┘  │                  │
                         │     │          │          │                  │
                         │     │  ┌───────────────┐  │   ┌────────────┐ │
                         │     │  │   intents     │  │   │metric_types│ │
                         │     │  └───────┬───────┘  │   └─────┬──────┘ │
                         └─────┼──────────┼──────────┼─────────┼────────┘
                               │          │          │         │
       ┌───────────────────────┼──────────┼──────────┼─────────┼────────┐
       │                       │          │          │         │        │
       │   sage_agent          │          │          │         │        │
       │   ┌──────────┐        │          │          │         │        │
       │   │ sessions │────────┘          │          │         │        │
       │   └────┬─────┘                   │          │         │        │
       │        │                         │          │         │        │
       │   ┌────▼─────┐                   │          │         │        │
       │   │ messages │←──── intent_slug ─┘          │         │        │
       │   └────┬─────┘                              │         │        │
       │        │                                    │         │        │
       │   ┌────▼─────────┐                          │         │        │
       │   │   feedback   │───── primary_category ───┘         │        │
       │   └──┬────────┬──┘                                    │        │
       │      │        │                                       │        │
       │   ┌──▼──┐  ┌──▼───────────────────┐                   │        │
       │   │embed│  │feedback_category_    │                   │        │
       │   │ ings│  │scores (multi-etiq.)  │                   │        │
       │   └─────┘  └──────────────────────┘                   │        │
       └───────────────────────────────────────────────────────┼────────┘
                                                               │
       ┌───────────────────────────────────────────────────────┼────────┐
       │   sage_analytics                                      │        │
       │   ┌─────────┐  ┌───────────────────┐                  │        │
       │   │ devices │  │ device_locations  │                  │        │
       │   └────┬────┘  └────────┬──────────┘                  │        │
       │        │                │                             │        │
       │   ┌────▼────────────────▼┐                            │        │
       │   │  xovis_raw_events    │                            │        │
       │   └────────────┬─────────┘                            │        │
       │                │                                      │        │
       │   ┌────────────▼─────────┐                            │        │
       │   │  normalized_metrics  │───── metric_type ──────────┘        │
       │   └────────────┬─────────┘                                     │
       │                │                                               │
       │   ┌────────────▼──────────┐                                    │
       │   │ person_count_records  │                                    │
       │   └───────────────────────┘                                    │
       └───────────────────────────────────────────────────────────────-┘

                       ▼ vistas materializadas que cruzan ambos ▼

                  ┌──────────────────────────────────┐
                  │           sage_views             │
                  │  - event_pulse_minute            │
                  │  - feedback_category_hourly      │
                  │  - intent_distribution_hourly    │
                  └──────────────────────────────────┘
```

### 4.3 Schemas — por qué hay cuatro

- **`sage_core`** — entidades compartidas. Cualquier cosa que ambos
  sistemas necesitan referenciar (`events`, `venues`, `locations`) y los
  catálogos estables (`feedback_categories`, `metric_types`, `intents`).
  Si esto cambia, cambia para los dos.
- **`sage_agent`** — todo lo que produce EVA. Si el equipo del agente
  rompe su modelo, no toca al de los sensores.
- **`sage_analytics`** — todo lo que produce `sage-analytics-api`. Mismo
  argumento simétrico.
- **`sage_views`** — vistas materializadas para análisis cross-fuente.
  No son fuente de verdad, son una caché — se pueden tirar y recrear sin
  pérdida.

Esto también facilita los permisos: el servicio del agente solo necesita
`USAGE` sobre `sage_core` + `WRITE` sobre `sage_agent`, y simétrico para
el de analytics.

### 4.4 Tablas — qué problema resuelve cada una

#### `sage_core.events`
La unidad de "edición del evento" — AHK 2026 es una fila. El JSONB
`config` guarda el equivalente al `DEFAULT_EVENT` de `event_store.py`
(agenda, FAQs, egresados, few-shot examples). El `slug` es el identificador
estable que usan ambos servicios. Trigger `updated_at` para auditoría.

#### `sage_core.venues` y `sage_core.locations`
Un venue agrupa zonas. Cada `location` tiene un `location_type`
restringido (`entrance`, `accreditation`, `main_hall`, `restroom`,
`emergency_exit`, …). **Esto es el ancla del cross-join entre los dos
sistemas:** cuando llega un `person_count` de Xovis, se asocia a la
location de su device; cuando un invitado deja feedback hablando de "la
entrada", una versión futura del clasificador podrá inferir la location
y permitir queries como _"feedback sobre la entrada vs aforo de la
entrada"_.

#### `sage_core.feedback_categories`, `metric_types`, `intents`
Catálogos. Pocas filas, muy estables, FK desde el resto. Tres ventajas:

- evitan typos (`'organizacion'` vs `'organización'`);
- se pueden activar/desactivar sin tocar código;
- el dashboard les pone el `label` legible.

#### `sage_agent.sessions`
Una conversación con EVA. Hoy `self.session_id` solo vive en memoria;
acá pasa a tener `started_at`, `ended_at`, qué `prompt_source` (hardcoded
vs dynamic) y qué modelo se usó. `client_metadata` JSONB para guardar
user-agent / locale / device sin tener que agregar columnas.

#### `sage_agent.messages`
**La tabla más importante del lado agente.** Cada turno (user/assistant)
es una fila. `turn_index` ordenado por sesión + unique con `role` para
no duplicar. Esto es lo que el `sage-agent` actual **no tiene** y es el
ancla que habilita "feedback sobre una respuesta específica" — el
`feedback.message_id` apunta acá.

Además guarda `intent_slug` + `intent_score` por mensaje user, lo que
permite analizar qué consultan los invitados sin tener que reprocesar
después (los intents se pierden hoy en stdout).

#### `sage_agent.feedback`
El feedback enriquecido de Analytics-SAGE persistido relacionalmente.
Una decisión deliberada: **un mensaje puede tener muchos feedbacks**
con `source` distintos:

- `auto_intent` — vino del intent matcher principal;
- `auto_detector` — vino del `FeedbackDetector` binario;
- `user_explicit` — thumbs up/down o rating dado por el invitado;
- `ia_team_manual` — corrección humana del equipo de IA.

`classifier_version` permite hacer A/B entre clasificadores y conservar
histórico cuando reclasifiquemos con un modelo nuevo. Las columnas
`happiness_score`, `net_promoter_score`, `return_likelihood_score`
mapean 1:1 al schema del JSON actual — la transición es directa.

#### `sage_agent.feedback_category_scores`
Multi-etiqueta con score y `rank`. Un feedback puede tener 3 filas acá
(catering rank=1, organización rank=2, recepción rank=3) sin pisarse.
El analista puede preguntar _"top 5 categorías mencionadas en feedbacks
con happiness < 4"_ sin parsear JSON.

#### `sage_agent.feedback_embeddings`
Tabla aparte porque los vectores son pesados y la mayoría de las queries
analíticas no los necesitan. **Esta es la pieza para clustering futuro y
para "encontrar quejas parecidas".** Índice ivfflat con `vector_cosine_ops`
para nearest-neighbor rápido. La dimensión `768` está alineada a
`nomic-embed-text` (el modelo que usa `app/embeddings.py`); si se cambia
el modelo, se ajusta la dimensión.

#### `sage_agent.jailbreak_attempts`
Hoy los jailbreaks bloqueados se imprimen a stdout y se pierden.
Acá quedan para análisis de seguridad y para mejorar el detector.

#### `sage_analytics.devices` y `device_locations`
Una cámara Xovis = una fila. `device_locations` es **history table** —
si una cámara se mueve de zona a mitad del evento, las métricas
históricas siguen referenciando la zona correcta por ventana de tiempo
(`valid_from`/`valid_to`). Sin esto, mover un sensor reescribiría el
significado del histórico.

#### `sage_analytics.xovis_raw_events`
El payload del POST de Xovis tal cual llegó, en JSONB. Indexado con GIN
para poder buscar dentro del JSON. Esto es **trazabilidad**: si aparece
un bug en el parser, podemos reprocesar el raw — no perdemos información.
Hoy esto se hace en disco (`data/raw-events/` o `/tmp` en Render);
en Postgres deja de ser efímero.

#### `sage_analytics.normalized_metrics`
Cada `NormalizedMetric` del API mapea 1:1 acá. `data` JSONB para el
payload normalizado completo, pero los campos importantes
(`event_id`, `location_id`, `metric_type`, `timestamp`) son columnas
con índices. El `timestamp` principal es `timestamp_to` cuando existe
(cierre de ventana Xovis), lo cual está alineado a la lógica de
`XovisParser` del API.

#### `sage_analytics.person_count_records`
Es una **proyección columnar** del `data{}` de `normalized_metrics` para
las queries más comunes (sumas de `forward_count`, `backward_count`,
filtros por `logic_id`). Se llena en el mismo insert que la métrica
normalizada — no es una segunda fuente de verdad. Permite hacer
`SUM(forward_count)` sin escanear JSONB.

### 4.5 Vistas materializadas — el cross-join

#### `sage_views.event_pulse_minute`
La query estrella. Combina, **minuto a minuto**, dos cosas:

- el flujo físico por location (ingress, egress, total_count);
- el clima emocional global del evento (count de feedbacks +
  promedios de happiness/NPS/return_likelihood).

Con esto un dashboard puede graficar la línea de NPS sobre la línea de
aforo y "ver" si el bajón coincidió con un pico de gente.

> Nota: el feedback hoy no tiene location asociada (no sabemos exactamente
> en qué zona estaba el invitado cuando dijo "la fila era larga"). Por
> ahora el JOIN deja `location_id = NULL` del lado feedback. Cuando el
> clasificador infiera la location, se actualiza esta vista para hacer
> el join también por zona.

#### `sage_views.feedback_category_hourly`
"¿De qué se está quejando la gente AHORA?". Por hora y categoría, número
de menciones, score promedio del match y happiness promedio para esa
categoría. Lo que un PM mira durante el evento.

#### `sage_views.intent_distribution_hourly`
"¿Qué consultan los invitados?". Útil para validar el system prompt
(_"a las 19 todos preguntan por baños — ¿tenemos suficiente cartelería?"_)
y para detectar si el `IntentMatcher` está dejando pasar muchos `NULL`
(intents no reconocidos).

### 4.6 Decisiones técnicas en breve

| Decisión | Por qué |
|---|---|
| UUID v4 en todas las PK | Genera el cliente (no necesita roundtrip), no expone orden de inserción, no choca entre fuentes |
| `TIMESTAMPTZ` siempre | Postgres convierte a UTC; sin esto los timestamps de Xovis (UTC) y EVA (local AR) se mezclan mal |
| `JSONB` para payload raw + metadata | Flexibilidad para campos opcionales sin migraciones por cada cambio menor |
| `pgvector` para embeddings | Búsqueda por similitud coseno con índice ivfflat — el JSONB no sirve para esto |
| Vistas materializadas (no normales) | El cross-join feedback↔Xovis es caro y se consulta seguido (dashboard); refrescar cada N minutos cuesta menos que cada query |
| Schemas separados (no todo en `public`) | Permisos por servicio, claridad de ownership |
| `ON CONFLICT DO NOTHING` en seed | El seed es re-ejecutable; aplicar dos veces no rompe |

### 4.7 Cómo ingestar datos

#### Desde EVA (Analytics-SAGE)

El módulo `app/db.py` ofrece tres funciones idempotentes:

- `ensure_session(session_id, prompt_source, model_name)` — al `__init__`
  del agente.
- `insert_message(...)` — en `agent.chat()`, después de cada turno.
- `insert_feedback(entry, message_id)` — en `feedback.save_feedback()`,
  después de calcular los scores.

Si `DATABASE_URL` no está configurada, las funciones son **no-op** y el
agente sigue funcionando con `feedback_log.json`. Esto permite migrar
sin downtime.

#### Desde `sage-analytics-api`

Ese repo tiene su propio módulo que va a cambiar próximamente para
escribir a Postgres. El contrato propuesto:

```python
# pseudocódigo
with conn.cursor() as cur:
    cur.execute("INSERT INTO sage_analytics.xovis_raw_events (...) VALUES (...) RETURNING id", ...)
    raw_id = cur.fetchone()["id"]
    for metric in normalized_metrics:
        cur.execute("INSERT INTO sage_analytics.normalized_metrics (raw_event_id, ...) ...", ...)
        cur.execute("INSERT INTO sage_analytics.person_count_records (metric_id, ...) ...", ...)
```

El mapping device → location se resuelve consultando `device_locations`
por ventana de tiempo (`valid_from <= NOW() < COALESCE(valid_to, 'infinity')`).

---

## 5. Cómo correrlo

### Levantar la base de datos

```bash
createdb sage_analytics
psql sage_analytics -f db/schema.sql
psql sage_analytics -f db/seed.sql
```

Si no tenés `pgvector` instalado, comentá la línea `CREATE EXTENSION ...
vector` y la tabla `sage_agent.feedback_embeddings` antes de aplicar.

### Levantar EVA con persistencia en Postgres

```bash
cp .env.example .env
# editar .env, descomentar DATABASE_URL
./run.sh
```

### Verificar

```bash
# Top categorías de feedback recibidas
psql sage_analytics -f db/sample_queries.sql
```

---

## 6. Próximos pasos sugeridos

- **Cablear `app/db.py` desde `agent.py` y `feedback.py`** — hoy las
  funciones existen pero el flujo del agente todavía escribe al JSON. La
  transición debería ser un toggle por env, escribir a ambos sinks
  durante una semana, y después solo Postgres.
- **Particionado por mes** en `xovis_raw_events` y `normalized_metrics`.
  En eventos chicos no hace falta, pero si SAGE crece a operar varios
  eventos al año, los índices van a degradar.
- **Inferir location del feedback** — cuando el clasificador semántico
  reconozca menciones de zona ("la entrada", "el salón"), grabar
  `location_id` en `feedback` y refactorear `event_pulse_minute` para
  hacer el join también por zona.
- **Job de refresh de vistas materializadas** — pgAgent o cron + psql,
  cada 1 minuto durante el evento, cada 1 hora fuera.
- **Endpoint de ingest en `sage-analytics-api`** que escriba a estas
  tablas en lugar de `data/raw-events/`. El contrato draft ya está
  documentado en su `docs/api-contract.md`.
- **Vector queries en producción** — exponer un endpoint
  `/feedback/similar?id=...` que use el índice ivfflat para encontrar
  quejas parecidas y permitir agrupación manual.

---

## 7. Mapeo entre los repos

| Concepto | Analytics-SAGE (este repo) | sage-analytics-api | Tabla en Postgres |
|---|---|---|---|
| Conversación | `agent.SageAgent.session_id` | — | `sage_agent.sessions` |
| Turno | `agent.history` (memoria) | — | `sage_agent.messages` |
| Feedback de invitado | `feedback_log.json` | — (recibirá vía API) | `sage_agent.feedback` |
| Categoría de feedback | `FEEDBACK_CATEGORY_EXAMPLES` | — | `sage_core.feedback_categories` |
| Embedding de feedback | (no persistido) | — | `sage_agent.feedback_embeddings` |
| Evento del demo | `event_store.DEFAULT_EVENT` | `event_id` (pasthrough) | `sage_core.events` |
| Zona del venue | `prompts.py` venue section | `location` (futuro) | `sage_core.locations` |
| Cámara Xovis | — | `Device` / `CameraMetadata` | `sage_analytics.devices` |
| Payload Xovis raw | — | `XovisRawEvent` + `data/raw-events/` | `sage_analytics.xovis_raw_events` |
| Métrica normalizada | — | `NormalizedMetric` | `sage_analytics.normalized_metrics` |
| Person count Logic Push | — | `PersonCountMetricData` | `sage_analytics.person_count_records` |

---

## Repos relacionados

- [`SAGE-AHK/sage-agent`](https://github.com/SAGE-AHK/sage-agent) — upstream del agente conversacional.
- [`SAGE-AHK/sage-analytics-api`](https://github.com/SAGE-AHK/sage-analytics-api) — API de ingesta Xovis.
- [`lucav12/Analytics-SAGE`](https://github.com/lucav12/Analytics-SAGE) — este repo.
