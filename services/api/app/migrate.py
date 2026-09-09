"""Apply the initial schema once when a managed PostgreSQL database is empty."""

from __future__ import annotations

import os
from pathlib import Path


def apply_initial_schema() -> None:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        return
    import psycopg

    with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.sources')")
        if cursor.fetchone()[0] is not None:
            return
        schema_path = Path(os.getenv("MIGRATION_PATH", Path(__file__).resolve().parents[3] / "infra" / "postgres" / "migrations" / "001_initial.sql"))
        cursor.execute(schema_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    apply_initial_schema()
