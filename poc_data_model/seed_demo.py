"""seed_demo.py — carga datos de demostración representativos.

Pobla las 5 tablas con:
  - 3 sesiones de conversación realistas (Spanish)
  - mensajes user/assistant con identidad estable (UUID)
  - feedbacks de los 4 sources distintos (auto_heuristic, auto_nlp,
    user_explicit, ia_team_manual)
  - UN mensaje con DOS feedbacks de clasificadores distintos
    → demuestra coexistencia A/B
  - UN embedding de ejemplo (vector dummy)

El objetivo es que `python demo_queries.py` después tenga datos sobre
los cuales correr analytics y mostrar el valor del modelo.
"""
from __future__ import annotations
import json
import sqlite3
import struct
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
DB_PATH = HERE / "sage_analytics.db"

# Hora base "del evento" — todos los timestamps son relativos a este momento.
EVENT_START = datetime(2026, 5, 30, 18, 0, tzinfo=timezone.utc)


def ts(minutes_after_start: int) -> str:
    return (EVENT_START + timedelta(minutes=minutes_after_start)).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def encode_vector(floats: list[float]) -> bytes:
    """Serializa un vector de floats a bytes (float32 little-endian).
    En SQLite va como BLOB. En Postgres+pgvector sería nativo."""
    return struct.pack(f"<{len(floats)}f", *floats)


def seed() -> None:
    if not DB_PATH.exists():
        raise SystemExit(
            "No existe sage_analytics.db. Corré primero: python build_db.py"
        )

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    # Limpiamos las tablas operacionales (NO el catálogo) por si seedeamos 2x
    for t in ("feedback_embeddings", "feedback", "messages", "sessions"):
        cur.execute(f"DELETE FROM {t}")

    # =========================================================================
    # SESIÓN 1 — invitado satisfecho, feedback positivo coexistente (v1 + v2)
    # =========================================================================
    s1 = new_id()
    cur.execute(
        "INSERT INTO sessions (id, started_at, ended_at, event_id, client_metadata) "
        "VALUES (?, ?, ?, ?, ?)",
        (s1, ts(0), ts(8), "diplomas-ahk-2026",
         json.dumps({"locale": "es-AR", "device": "ipad-recepción-01"}))
    )

    # turno 1: saludo
    m1u, m1a = new_id(), new_id()
    cur.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at, turn_index) "
        "VALUES (?, ?, 'user', ?, ?, 1)",
        (m1u, s1, "hola", ts(0))
    )
    cur.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at, turn_index, "
        "parent_message_id, model_name, token_count, latency_ms) "
        "VALUES (?, ?, 'assistant', ?, ?, 1, ?, ?, ?, ?)",
        (m1a, s1,
         "¡Bienvenido a la Entrega de Diplomas AHK 2026! Soy EVA. ¿En qué puedo ayudarte?",
         ts(0), m1u, "llama3.2:3b", 32, 1420)
    )

    # turno 2: pregunta logística
    m2u, m2a = new_id(), new_id()
    cur.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at, turn_index) "
        "VALUES (?, ?, 'user', ?, ?, 2)",
        (m2u, s1, "¿dónde está el guardarropa?", ts(2))
    )
    cur.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at, turn_index, "
        "parent_message_id, model_name, token_count, latency_ms) "
        "VALUES (?, ?, 'assistant', ?, ?, 2, ?, ?, ?, ?)",
        (m2a, s1,
         "El guardarropa está en planta baja, a la izquierda de la entrada.",
         ts(2), m2u, "llama3.2:3b", 18, 980)
    )

    # turno 3: feedback positivo del invitado
    m3u, m3a = new_id(), new_id()
    cur.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at, turn_index) "
        "VALUES (?, ?, 'user', ?, ?, 3)",
        (m3u, s1, "la ceremonia estuvo muy emocionante, felicitar al equipo", ts(7))
    )
    cur.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at, turn_index, "
        "parent_message_id, model_name, token_count, latency_ms) "
        "VALUES (?, ?, 'assistant', ?, ?, 3, ?, ?, ?, ?)",
        (m3a, s1,
         "¡Qué alegría escuchar eso! Le voy a transmitir tu felicitación al equipo organizador.",
         ts(7), m3u, "llama3.2:3b", 25, 1180)
    )

    # FEEDBACK A: clasificador heurístico v1 (lo que ya hace feedback.py)
    fb1 = new_id()
    cur.execute(
        "INSERT INTO feedback (id, message_id, session_id, source, classifier_version, "
        "sentiment_label, category, raw_signal, created_at, processed_at) "
        "VALUES (?, ?, ?, 'auto_heuristic', 'keyword-v1', 'positive', 'ceremonia', ?, ?, ?)",
        (fb1, m3a, s1, "la ceremonia estuvo muy emocionante, felicitar al equipo",
         ts(7), ts(7))
    )

    # FEEDBACK B: clasificador NLP v2 sobre el MISMO mensaje (coexistencia)
    fb2 = new_id()
    cur.execute(
        "INSERT INTO feedback (id, message_id, session_id, source, classifier_version, "
        "sentiment_label, sentiment_score, category, confidence, raw_signal, created_at, processed_at, metadata) "
        "VALUES (?, ?, ?, 'auto_nlp', 'embeddings-v2', 'positive', ?, 'ceremonia', ?, ?, ?, ?, ?)",
        (fb2, m3a, s1, 0.88, 0.94,
         "la ceremonia estuvo muy emocionante, felicitar al equipo",
         ts(8), ts(8),
         json.dumps({"model": "paraphrase-multilingual-MiniLM-L12-v2", "tokens": 11}))
    )

    # Embedding de ejemplo asociado al feedback NLP (vector dummy 8-dim)
    cur.execute(
        "INSERT INTO feedback_embeddings (feedback_id, model_name, dimensions, vector, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (fb2, "paraphrase-multilingual-MiniLM-L12-v2 (dummy)", 8,
         encode_vector([0.12, -0.34, 0.51, 0.08, -0.22, 0.45, 0.31, -0.19]),
         ts(8))
    )

    # FEEDBACK C: el invitado tocó 👍 en la respuesta del agente (explícito UI)
    fb3 = new_id()
    cur.execute(
        "INSERT INTO feedback (id, message_id, session_id, source, classifier_version, "
        "thumbs, raw_signal, created_at) "
        "VALUES (?, ?, ?, 'user_explicit', 'ui-v1', 'up', ?, ?)",
        (fb3, m3a, s1, "[thumbs-up sin comentario]", ts(8))
    )

    # =========================================================================
    # SESIÓN 2 — feedback mixto (catering bien, organización mal)
    # =========================================================================
    s2 = new_id()
    cur.execute(
        "INSERT INTO sessions (id, started_at, ended_at, event_id, client_metadata) "
        "VALUES (?, ?, ?, ?, ?)",
        (s2, ts(15), ts(22), "diplomas-ahk-2026",
         json.dumps({"locale": "es-AR", "device": "ipad-recepción-02"}))
    )

    m4u, m4a = new_id(), new_id()
    cur.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at, turn_index) "
        "VALUES (?, ?, 'user', ?, ?, 1)",
        (m4u, s2, "¿a qué hora es la foto grupal?", ts(15))
    )
    cur.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at, turn_index, "
        "parent_message_id, model_name, token_count, latency_ms) "
        "VALUES (?, ?, 'assistant', ?, ?, 1, ?, ?, ?, ?)",
        (m4a, s2,
         "La foto grupal está agendada a las 19:45, después de la entrega de diplomas.",
         ts(15), m4u, "llama3.2:3b", 22, 1100)
    )

    m5u, m5a = new_id(), new_id()
    cur.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at, turn_index) "
        "VALUES (?, ?, 'user', ?, ?, 2)",
        (m5u, s2, "el catering estuvo bueno pero la espera fue muy larga", ts(20))
    )
    cur.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at, turn_index, "
        "parent_message_id, model_name, token_count, latency_ms) "
        "VALUES (?, ?, 'assistant', ?, ?, 2, ?, ?, ?, ?)",
        (m5a, s2,
         "Gracias por compartirlo. Tomamos nota del comentario sobre los tiempos.",
         ts(20), m5u, "llama3.2:3b", 19, 1010)
    )

    # Feedback v1 sobre este mensaje: la heurística keyword-v1 le pone 'positivo'
    # (porque cuenta 'bueno' positivo y 'larga' negativo → empata o gana positivo).
    # Es el bug que mencionamos en el doc — lo dejamos para que se vea.
    fb4 = new_id()
    cur.execute(
        "INSERT INTO feedback (id, message_id, session_id, source, classifier_version, "
        "sentiment_label, category, raw_signal, created_at, processed_at) "
        "VALUES (?, ?, ?, 'auto_heuristic', 'keyword-v1', 'positive', 'catering', ?, ?, ?)",
        (fb4, m5a, s2, "el catering estuvo bueno pero la espera fue muy larga",
         ts(20), ts(20))
    )

    # Feedback v2 sobre el MISMO mensaje: NLP lo clasifica correctamente 'mixed'
    fb5 = new_id()
    cur.execute(
        "INSERT INTO feedback (id, message_id, session_id, source, classifier_version, "
        "sentiment_label, sentiment_score, category, confidence, raw_signal, created_at, processed_at) "
        "VALUES (?, ?, ?, 'auto_nlp', 'embeddings-v2', 'mixed', ?, 'catering', ?, ?, ?, ?)",
        (fb5, m5a, s2, 0.05, 0.81,
         "el catering estuvo bueno pero la espera fue muy larga", ts(21), ts(21))
    )

    # Feedback explícito: el usuario tocó 👎 en la respuesta del agente
    fb6 = new_id()
    cur.execute(
        "INSERT INTO feedback (id, message_id, session_id, source, classifier_version, "
        "thumbs, rating, comment, raw_signal, created_at) "
        "VALUES (?, ?, ?, 'user_explicit', 'ui-v1', 'down', 2, ?, ?, ?)",
        (fb6, m5a, s2, "esperaba que pudiera escalar la queja", "[thumbs-down]", ts(22))
    )

    # =========================================================================
    # SESIÓN 3 — feedback negativo + corrección manual del equipo IA
    # =========================================================================
    s3 = new_id()
    cur.execute(
        "INSERT INTO sessions (id, started_at, ended_at, event_id, client_metadata) "
        "VALUES (?, ?, ?, ?, ?)",
        (s3, ts(30), None, "diplomas-ahk-2026",  # ended_at=None → sesión en curso
         json.dumps({"locale": "es-AR", "device": "ipad-recepción-01"}))
    )

    m6u, m6a = new_id(), new_id()
    cur.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at, turn_index) "
        "VALUES (?, ?, 'user', ?, ?, 1)",
        (m6u, s3,
         "no me gustó la organización, demasiado caos en la entrada y la acreditación lentísima",
         ts(30))
    )
    cur.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at, turn_index, "
        "parent_message_id, model_name, token_count, latency_ms) "
        "VALUES (?, ?, 'assistant', ?, ?, 1, ?, ?, ?, ?)",
        (m6a, s3,
         "Lamento mucho la experiencia. Le voy a transmitir tu comentario al equipo de logística.",
         ts(30), m6u, "llama3.2:3b", 24, 1330)
    )

    # heurística v1: el bug clásico — la frase tiene 'no me gustó' (que matchea
    # tanto 'me gustó' positivo como 'no me gustó' negativo) → empata = neutro
    fb7 = new_id()
    cur.execute(
        "INSERT INTO feedback (id, message_id, session_id, source, classifier_version, "
        "sentiment_label, category, raw_signal, created_at, processed_at) "
        "VALUES (?, ?, ?, 'auto_heuristic', 'keyword-v1', 'neutral', 'organización', ?, ?, ?)",
        (fb7, m6a, s3,
         "no me gustó la organización, demasiado caos en la entrada y la acreditación lentísima",
         ts(30), ts(30))
    )

    # NLP v2 lo clasifica correctamente como 'negative' con alta confianza
    fb8 = new_id()
    cur.execute(
        "INSERT INTO feedback (id, message_id, session_id, source, classifier_version, "
        "sentiment_label, sentiment_score, category, confidence, raw_signal, created_at, processed_at) "
        "VALUES (?, ?, ?, 'auto_nlp', 'embeddings-v2', 'negative', ?, 'organización', ?, ?, ?, ?)",
        (fb8, m6a, s3, -0.78, 0.91,
         "no me gustó la organización, demasiado caos en la entrada y la acreditación lentísima",
         ts(31), ts(31))
    )

    # corrección manual del equipo IA: agregan subcategoría 'acreditación'
    # (se hace como UN NUEVO ROW source=ia_team_manual; no se pisa lo anterior)
    fb9 = new_id()
    cur.execute(
        "INSERT INTO feedback (id, message_id, session_id, source, classifier_version, "
        "sentiment_label, category, subcategory, comment, raw_signal, created_at, processed_at) "
        "VALUES (?, ?, ?, 'ia_team_manual', 'review-v1', 'negative', 'organización', "
        "'acreditación', 'caso para escalar a logística', ?, ?, ?)",
        (fb9, m6a, s3,
         "no me gustó la organización, demasiado caos en la entrada y la acreditación lentísima",
         ts(35), ts(35))
    )

    conn.commit()

    # Resumen
    counts = {}
    for t in ("sessions", "messages", "feedback", "feedback_embeddings"):
        counts[t] = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    conn.close()

    print("[+] Seed completo:")
    for t, n in counts.items():
        print(f"    {t:<22} {n}")


if __name__ == "__main__":
    seed()
