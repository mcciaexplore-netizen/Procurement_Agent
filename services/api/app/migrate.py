"""Apply the initial schema once when a managed PostgreSQL database is empty."""

from __future__ import annotations

import os
from pathlib import Path


def initial_schema_path() -> Path:
    configured = os.getenv("MIGRATION_PATH")
    if configured:
        return Path(configured)
    module_path = Path(__file__).resolve()
    for candidate in module_path.parents:
        migration = candidate / "infra" / "postgres" / "migrations" / "001_initial.sql"
        if migration.is_file():
            return migration
    raise FileNotFoundError("initial PostgreSQL migration was not found")


def apply_initial_schema() -> None:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not configured; starting in demonstration persistence mode.", flush=True)
        return
    import psycopg

    print("Checking PostgreSQL schema…", flush=True)
    with psycopg.connect(dsn, connect_timeout=10) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.sources')")
        if cursor.fetchone()[0] is not None:
            print("PostgreSQL schema is ready.", flush=True)
            return
        schema_path = initial_schema_path()
        print("Applying initial PostgreSQL schema…", flush=True)
        cursor.execute(schema_path.read_text(encoding="utf-8"))
        print("Initial PostgreSQL schema is ready.", flush=True)


if __name__ == "__main__":
    apply_initial_schema()
