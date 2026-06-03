"""Capa fina de acceso a Postgres para EVA.

Hoy `feedback.py` persiste en un JSON (`feedback_log.json`); este módulo
provee el camino para apuntarlo a Postgres sin tocar el resto del flujo.

Si `DATABASE_URL` no está definida, las funciones son no-op — el agente sigue
funcionando con el sink JSON heredado. Cuando la URL esté seteada, los
inserts van a Postgres usando el modelo definido en `db/schema.sql`.

No se usa SQLAlchemy ORM a propósito: el módulo `feedback.py` ya construye
el dict del feedback con todos sus campos, así que con psycopg + SQL plano
alcanza y queda más legible.
"""

import json
import os
from contextlib import contextmanager
from typing import Any, Iterator

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # psycopg es opcional hasta que se conecte Postgres
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
EVENT_SLUG = os.getenv("SAGE_EVENT_SLUG", "ahk-diplomas-2026")
CLASSIFIER_VERSION = os.getenv("SAGE_CLASSIFIER_VERSION", "embeddings-v1")


def is_enabled() -> bool:
    return bool(DATABASE_URL) and psycopg is not None


@contextmanager
def get_conn() -> Iterator[Any]:
    if not is_enabled():
        raise RuntimeError("DATABASE_URL no está configurada o psycopg no está instalado.")
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        yield conn


def _resolve_event_id(conn) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM sage_core.events WHERE slug = %s LIMIT 1",
            (EVENT_SLUG,),
        )
        row = cur.fetchone()
        return row["id"] if row else None


def ensure_session(session_id: str, prompt_source: str, model_name: str | None) -> None:
    """Crea la sesión si todavía no existe (idempotente)."""
    if not is_enabled():
        return
    with get_conn() as conn:
        event_id = _resolve_event_id(conn)
        if not event_id:
            return
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sage_agent.sessions (id, event_id, prompt_source, model_name)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (session_id, event_id, prompt_source, model_name),
            )


def insert_message(
    message_id: str,
    session_id: str,
    role: str,
    content: str,
    turn_index: int,
    intent_slug: str | None = None,
    intent_score: float | None = None,
    token_count: int | None = None,
    latency_ms: int | None = None,
    parent_message_id: str | None = None,
) -> None:
    if not is_enabled():
        return
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sage_agent.messages
                (id, session_id, role, content, turn_index, parent_message_id,
                 intent_slug, intent_score, token_count, latency_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                message_id, session_id, role, content, turn_index, parent_message_id,
                intent_slug, intent_score, token_count, latency_ms,
            ),
        )


def insert_feedback(entry: dict, message_id: str, source: str = "auto_detector") -> str | None:
    """Persistir un feedback en Postgres.

    `entry` es el dict que produce `feedback.save_feedback()`, con sus
    categorías, scores y el texto del invitado. `message_id` es el UUID del
    mensaje user que originó el feedback (FK a sage_agent.messages).
    """
    if not is_enabled():
        return None

    feedback_id = entry["id"]
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sage_agent.feedback (
                id, session_id, message_id,
                source, classifier_version, primary_category,
                happiness_score, net_promoter_score, return_likelihood_score,
                raw_signal, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                feedback_id,
                entry["session_id"],
                message_id,
                source,
                CLASSIFIER_VERSION,
                entry.get("categoria"),
                entry.get("happiness_score"),
                entry.get("net_promoter_score"),
                entry.get("return_likelihood_score"),
                entry["mensaje_invitado"],
                json.dumps({
                    "respuesta_eva": entry.get("respuesta_eva"),
                    "categorias": entry.get("categorias", []),
                }),
            ),
        )
        for rank, cs in enumerate(entry.get("categorias_scores", []), start=1):
            cur.execute(
                """
                INSERT INTO sage_agent.feedback_category_scores
                    (feedback_id, category_slug, score, rank)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (feedback_id, category_slug) DO NOTHING
                """,
                (feedback_id, cs["categoria"], cs["score"], rank),
            )
    return feedback_id
