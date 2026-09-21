from pathlib import Path

from app.migrate import initial_schema_path


def test_initial_schema_path_prefers_configured_container_path(tmp_path: Path, monkeypatch) -> None:
    configured = tmp_path / "schema.sql"
    monkeypatch.setenv("MIGRATION_PATH", str(configured))

    assert initial_schema_path() == configured
