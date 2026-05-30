"""demo_queries.py — corre queries analíticas sobre los datos de seed.

Cada bloque imprime el query SQL y su resultado tabulado. La idea es
mostrar que el modelo de datos habilita analytics reales con SQL plano
— sin necesidad de un ORM ni de procesamiento extra en Python.

Queries incluidos:
  1. Distribución de feedback por sentimiento (global)
  2. Top categorías por volumen
  3. Acuerdo / desacuerdo entre clasificadores (heurística vs NLP)
  4. Respuestas del agente con feedback negativo (input para iterar prompt)
  5. Timeline de feedback por sesión
  6. CSAT (satisfacción) usando solo el clasificador NLP v2
"""
from __future__ import annotations
import sqlite3
from pathlib import Path

HERE = Path(__file__).parent
DB_PATH = HERE / "sage_analytics.db"


def banner(title: str) -> None:
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


def print_sql(sql: str) -> None:
    print("\n-- SQL:")
    for line in sql.strip().splitlines():
        print(f"   {line}")
    print()


def run(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return list(conn.execute(sql, params))


def render(rows: list[sqlite3.Row], headers: list[str], widths: list[int]) -> None:
    line = " | ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(line)
    print("-" * len(line))
    for r in rows:
        cells = []
        for v, w in zip(r, widths):
            s = "" if v is None else str(v)
            if len(s) > w:
                s = s[: w - 1] + "…"
            cells.append(s.ljust(w))
        print(" | ".join(cells))
    if not rows:
        print("(sin resultados)")


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit("Falta sage_analytics.db. Corré: python build_db.py && python seed_demo.py")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # -----------------------------------------------------------------------
    banner("1) Distribución de feedback por sentimiento (todos los clasificadores)")
    sql = """
    SELECT sentiment_label, COUNT(*) AS n
    FROM feedback
    WHERE sentiment_label IS NOT NULL
    GROUP BY sentiment_label
    ORDER BY n DESC
    """
    print_sql(sql)
    render(run(conn, sql), ["sentiment_label", "n"], [20, 6])

    # -----------------------------------------------------------------------
    banner("2) Top categorías por volumen de feedback")
    sql = """
    SELECT category, COUNT(*) AS n_feedback
    FROM feedback
    WHERE category IS NOT NULL
    GROUP BY category
    ORDER BY n_feedback DESC
    """
    print_sql(sql)
    render(run(conn, sql), ["category", "n_feedback"], [20, 12])

    # -----------------------------------------------------------------------
    banner("3) Acuerdo / desacuerdo entre clasificadores sobre el MISMO mensaje")
    print("   (Para auditar la calidad del nuevo NLP vs la heurística vieja.)")
    sql = """
    SELECT
        a.message_id,
        a.sentiment_label AS heuristic_v1,
        b.sentiment_label AS nlp_v2,
        CASE WHEN a.sentiment_label = b.sentiment_label
             THEN 'agree' ELSE 'DISAGREE' END AS verdict
    FROM feedback a
    JOIN feedback b
      ON a.message_id = b.message_id
     AND a.source = 'auto_heuristic'
     AND b.source = 'auto_nlp'
    """
    print_sql(sql)
    render(run(conn, sql),
           ["message_id", "heuristic_v1", "nlp_v2", "verdict"],
           [38, 14, 14, 10])

    # -----------------------------------------------------------------------
    banner("4) Respuestas del agente con feedback negativo (input para iterar el prompt)")
    sql = """
    SELECT
        m.id           AS message_id,
        substr(m.content, 1, 60) AS respuesta_eva,
        f.sentiment_label AS sentiment,
        f.category,
        f.source
    FROM feedback f
    JOIN messages m ON m.id = f.message_id
    WHERE f.sentiment_label = 'negative'
      AND m.role = 'assistant'
    ORDER BY f.created_at DESC
    """
    print_sql(sql)
    render(run(conn, sql),
           ["message_id", "respuesta_eva", "sentiment", "category", "source"],
           [38, 60, 10, 14, 16])

    # -----------------------------------------------------------------------
    banner("5) Timeline de feedback por sesión")
    sql = """
    SELECT
        s.id                            AS session_id,
        s.started_at                    AS session_start,
        COUNT(f.id)                     AS n_feedback,
        SUM(CASE WHEN f.sentiment_label='positive' THEN 1 ELSE 0 END) AS pos,
        SUM(CASE WHEN f.sentiment_label='negative' THEN 1 ELSE 0 END) AS neg,
        SUM(CASE WHEN f.thumbs='down'              THEN 1 ELSE 0 END) AS thumbs_down
    FROM sessions s
    LEFT JOIN feedback f ON f.session_id = s.id
    GROUP BY s.id, s.started_at
    ORDER BY s.started_at
    """
    print_sql(sql)
    render(run(conn, sql),
           ["session_id", "session_start", "n_feedback", "pos", "neg", "thumbs_down"],
           [38, 28, 11, 4, 4, 12])

    # -----------------------------------------------------------------------
    banner("6) CSAT (% positivo sobre etiquetados) usando SOLO el NLP v2")
    print("   Demostración de por qué importa `classifier_version`: filtramos.")
    sql = """
    SELECT
        ROUND(
          1.0 * SUM(CASE WHEN sentiment_label = 'positive' THEN 1 ELSE 0 END)
          / NULLIF(SUM(CASE WHEN sentiment_label IN ('positive','negative') THEN 1 ELSE 0 END), 0),
          3
        ) AS csat_nlp_v2,
        COUNT(*) AS n_total
    FROM feedback
    WHERE source = 'auto_nlp'
      AND classifier_version = 'embeddings-v2'
    """
    print_sql(sql)
    render(run(conn, sql), ["csat_nlp_v2", "n_total"], [14, 8])

    conn.close()
    print()
    print("[+] Fin de la demo. Modificá seed_demo.py para sumar más casos.")


if __name__ == "__main__":
    main()
