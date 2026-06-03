# Analytics-SAGE

Fork del agente conversacional [`SAGE-AHK/sage-agent`](https://github.com/SAGE-AHK/sage-agent)
con un clasificador de feedback enriquecido (multi-categoría + scores de
happiness, NPS y probabilidad de retorno) y un modelo de datos PostgreSQL
que lo integra con [`SAGE-AHK/sage-analytics-api`](https://github.com/SAGE-AHK/sage-analytics-api).

## Lectura

- **[`DOC.md`](DOC.md)** — documentación técnica completa. Explica el
  sync con upstream, el clasificador de feedback enriquecido y, sobre
  todo, **el modelo de datos**.
- **[`db/README.md`](db/README.md)** — cómo aplicar el schema.
- **[`db/schema.sql`](db/schema.sql)** — DDL del modelo integrado.
- **[`db/sample_queries.sql`](db/sample_queries.sql)** — queries
  cross-fuente de referencia.

## Quick start

```bash
# 1. Levantar la base de datos
createdb sage_analytics
psql sage_analytics -f db/schema.sql
psql sage_analytics -f db/seed.sql

# 2. Configurar el agente
cp .env.example .env
# editar .env: DATABASE_URL, PIPER_BIN, PIPER_MODEL, OLLAMA_MODEL

# 3. Correr EVA
./run.sh
```

Detalle de instalación de Ollama, Piper TTS y el modelo de embeddings:
ver el [README de `sage-agent`](https://github.com/SAGE-AHK/sage-agent#readme).

## Estructura

```
.
├── DOC.md                  ← documentación principal
├── README.md               ← este archivo
├── Dockerfile
├── run.sh
├── requirements.txt
├── .env.example
├── app/
│   ├── main.py             API FastAPI (chat, TTS, /configure)
│   ├── agent.py            Lógica del agente, jailbreak, intents
│   ├── embeddings.py       IntentMatcher + FeedbackDetector
│   ├── feedback.py         Clasificador enriquecido + scores
│   ├── prompts.py          System prompt hardcodeado (modo demo)
│   ├── prompt_builder.py   Prompt desde JSON estructurado (modo dynamic)
│   ├── event_store.py      Persistencia del evento activo
│   ├── db.py               Capa fina Postgres (opt-in vía DATABASE_URL)
│   └── test_embeddings.py
└── db/
    ├── schema.sql          DDL integrado
    ├── seed.sql            Catálogos + evento demo
    ├── sample_queries.sql
    ├── README.md
    └── migrations/
        └── 0001_init.sql
```
