"""build_db.py — crea la base SQLite desde schema.sql.

Uso:
    python build_db.py            # crea sage_analytics.db en esta carpeta
    python build_db.py --reset    # borra la DB existente antes de crearla

La DB se genera al lado del script (no en el home). Es local y descartable;
está en .gitignore.
"""
from __future__ import annotations
import argparse
import sqlite3
from pathlib import Path

HERE = Path(__file__).parent
DB_PATH = HERE / "sage_analytics.db"
SCHEMA_PATH = HERE / "schema.sql"


def build(reset: bool = False) -> None:
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
        print(f"[-] DB previa eliminada: {DB_PATH.name}")

    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(sql)
        conn.commit()

    # Verificación rápida
    with sqlite3.connect(DB_PATH) as conn:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )]
    print(f"[+] DB creada: {DB_PATH}")
    print(f"    Tablas: {', '.join(tables)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true",
                    help="Borrar la DB existente antes de crear")
    args = ap.parse_args()
    build(reset=args.reset)
