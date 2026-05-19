"""
feedback_api.py
================

Respuesta directa al pedido del equipo IA (Martin):

  1) Categorías + criterios de evaluación acordados — base para que IA
     derive el listado de palabras clave del detector.
  2) Estructura (no modelo de datos cerrado) sobre la que se asienta la
     DB definitiva. Está expresada como un schema Pydantic: si esto
     cambia, cambia la tabla; si esto queda fijo, la migración a Postgres
     después es mecánica.
  3) Un único endpoint POST /feedback que recibe una fila ya formateada
     desde el pipeline del modelo y la persiste.

Lo que NO hace (a propósito, porque no lo pidió):
  - cambiar /chat ni tocar SageAgent
  - clasificación NLP, embeddings, workers
  - dashboards o queries de analytics
  - autenticación

Cómo correrlo LOCAL (sin tocar el repo público):

    # 1) instalar dependencias (una vez, en tu venv local)
    pip install "fastapi>=0.115" "uvicorn[standard]>=0.30" "pydantic>=2.7"

    # 2) levantar
    python feedback_api.py
    # o:   uvicorn feedback_api:app --reload

    # 3) abrir Swagger
    #    http://localhost:8000/docs

Cómo lo usaría Martin desde el modelo (cuando lo conectemos):

    POST http://localhost:8000/feedback
    Content-Type: application/json
    {
      "raw_signal": "el catering estuvo bueno pero la espera fue larga",
      "category": "organización",
      "sentiment": "mixed",
      "source": "auto_nlp",
      "classifier_version": "embeddings-v2",
      "confidence": 0.82
    }

Persistencia: SQLite local (feedback.db al lado del archivo). Cuando se
migre a Postgres solo cambian `_connect` y los tipos del CREATE TABLE;
los nombres y semántica de los campos quedan iguales.

Integración al repo `sage-agent` cuando estemos listos (NO ahora):

    # app/main.py
    from feedback_api import router as feedback_router
    app.include_router(feedback_router)
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 1) CATEGORÍAS Y CRITERIOS DE EVALUACIÓN
# ---------------------------------------------------------------------------
# Acuerdo propuesto. El equipo IA arma su listado de palabras clave
# alineado a estas categorías; si quieren agregar/sacar, se edita acá y
# se versiona. El `slug` (la key) es lo que se guarda en DB y debe
# mantenerse estable.

CATEGORIES: dict[str, str] = {
    "ceremonia":    "Acto en sí: diplomas, discursos, palabras de autoridades",
    "organización": "Logística, puntualidad, orden, esperas, demoras",
    "recepción":    "Llegada, entrada, acreditación, bienvenida",
    "catering":     "Comida, bebida, buffet, networking food",
    "contenido":    "Calidad/exactitud de la información que dio EVA",
    "agente":       "Experiencia conversacional con EVA (claridad, tono, latencia)",
    "general":      "No encaja en las anteriores",
}

# Criterios de evaluación = ejes sobre los que se clasifica cada feedback.
# - sentiment: qué siente el invitado.
# - intensity: qué tan fuerte (opcional, útil si IA lo puede inferir).
# - source:    quién emitió esta clasificación (clave para A/B y para
#              que coexistan heurística + NLP sin pisarse).

SENTIMENTS  = ("positive", "negative", "neutral", "mixed")
INTENSITIES = ("low", "medium", "high")
SOURCES = (
    "auto_heuristic",   # detector keyword actual (feedback.py)
    "auto_nlp",         # clasificador semántico de Martin
    "user_explicit",    # thumbs/rating desde la UI
    "ia_team_manual",   # corrección humana del equipo IA
)


# ---------------------------------------------------------------------------
# 2) ESTRUCTURA — Pydantic. Esta es la "forma" sobre la que se asienta el
# modelo de datos. Pensar de acá para abajo, no al revés.
# ---------------------------------------------------------------------------

class FeedbackIn(BaseModel):
    """Lo que el equipo IA postea. Diseñado para que la fila ya venga
    'casi lista' y el backend solo agregue `id` y `created_at`."""

    # --- Identidad del turno al que el feedback se refiere -----------------
    # Hoy son opcionales porque /chat todavía no devuelve message_id; en
    # cuanto se agregue, pasan a ser obligatorios.
    message_id: Optional[uuid.UUID] = Field(
        default=None,
        description="ID de la respuesta del agente evaluada.",
    )
    session_id: Optional[uuid.UUID] = Field(
        default=None,
        description="ID de sesión (SageAgent.session_id).",
    )

    # --- Señal observada ---------------------------------------------------
    raw_signal: str = Field(
        min_length=1, max_length=4000,
        description=(
            "Texto que disparó el feedback (mensaje del invitado, comentario "
            "libre, etc.). Se guarda siempre, para auditoría y reclasificación."
        ),
    )

    # --- Clasificación -----------------------------------------------------
    category: Optional[Literal[
        "ceremonia", "organización", "recepción",
        "catering", "contenido", "agente", "general"
    ]] = None
    sentiment: Optional[Literal["positive", "negative", "neutral", "mixed"]] = None
    sentiment_score: Optional[float] = Field(
        default=None, ge=-1.0, le=1.0,
        description="Score numérico alineado con `sentiment` (opcional).",
    )
    intensity: Optional[Literal["low", "medium", "high"]] = None

    # --- Trazabilidad del clasificador ------------------------------------
    source: Literal[
        "auto_heuristic", "auto_nlp", "user_explicit", "ia_team_manual"
    ] = Field(description="Quién/qué generó este feedback row.")
    classifier_version: str = Field(
        min_length=1, max_length=64,
        description=(
            "Identificador del clasificador, ej. 'keyword-v1', 'embeddings-v2'. "
            "Permite que conviva más de una versión sin sobrescribir histórico."
        ),
    )
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    # --- Comentario humano opcional ---------------------------------------
    comment: Optional[str] = Field(default=None, max_length=2000)

    model_config = ConfigDict(extra="forbid")


class FeedbackOut(FeedbackIn):
    """Lo que devuelve la API: el payload de entrada + lo que asigna el server."""
    id: uuid.UUID
    created_at: datetime


# ---------------------------------------------------------------------------
# 3) PERSISTENCIA — SQLite local, suficiente para arrancar.
# Migración a Postgres: cambia `_connect` (psycopg/asyncpg) y los tipos
# del CREATE TABLE (TEXT→UUID/TIMESTAMPTZ). Nombres de columnas iguales.
# ---------------------------------------------------------------------------

DB_PATH = Path(__file__).parent / "feedback.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback (
    id                  TEXT PRIMARY KEY,
    message_id          TEXT,
    session_id          TEXT,
    raw_signal          TEXT NOT NULL,
    category            TEXT,
    sentiment           TEXT,
    sentiment_score     REAL,
    intensity           TEXT,
    source              TEXT NOT NULL,
    classifier_version  TEXT NOT NULL,
    confidence          REAL,
    comment             TEXT,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_message    ON feedback(message_id);
CREATE INDEX IF NOT EXISTS idx_feedback_session    ON feedback(session_id);
CREATE INDEX IF NOT EXISTS idx_feedback_category   ON feedback(category);
CREATE INDEX IF NOT EXISTS idx_feedback_sentiment  ON feedback(sentiment);
CREATE INDEX IF NOT EXISTS idx_feedback_source_ver ON feedback(source, classifier_version);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)


_init_db()


def _insert(row: FeedbackOut) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO feedback (
                id, message_id, session_id, raw_signal,
                category, sentiment, sentiment_score, intensity,
                source, classifier_version, confidence, comment, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(row.id),
                str(row.message_id) if row.message_id else None,
                str(row.session_id) if row.session_id else None,
                row.raw_signal,
                row.category,
                row.sentiment,
                row.sentiment_score,
                row.intensity,
                row.source,
                row.classifier_version,
                row.confidence,
                row.comment,
                row.created_at.isoformat(),
            ),
        )


# ---------------------------------------------------------------------------
# 4) API — un endpoint para insertar + uno auxiliar para leer el catálogo
# de categorías (para que IA lo consulte y alinee sus keywords).
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
def insert_feedback(payload: FeedbackIn) -> FeedbackOut:
    """Inserta una fila de feedback ya formateada por el equipo IA.

    El backend solo agrega `id` y `created_at`. No clasifica ni
    re-procesa: confía en el clasificador que envió el payload (lo
    identifica `source` + `classifier_version`).
    """
    out = FeedbackOut(
        id=uuid.uuid4(),
        created_at=datetime.now(timezone.utc),
        **payload.model_dump(),
    )
    try:
        _insert(out)
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"db error: {exc}",
        )
    return out


@router.get("/categories")
def list_categories() -> dict[str, str]:
    """Catálogo de categorías acordado. IA lo consulta para alinear su
    listado de palabras clave."""
    return CATEGORIES


# ---------------------------------------------------------------------------
# 5) APP STANDALONE — para correr local sin tocar el repo público.
# Cuando se integre a sage-agent esto sobra; mientras tanto, hace el
# archivo ejecutable por sí solo.
# ---------------------------------------------------------------------------

app = FastAPI(title="SAGE Feedback API (local dev)")
app.include_router(router)


@app.get("/")
def health() -> dict[str, str]:
    return {"status": "feedback-api online", "db": str(DB_PATH)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
