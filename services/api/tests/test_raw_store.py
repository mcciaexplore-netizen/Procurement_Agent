from pathlib import Path

from app.application.raw_store import FilesystemRawCaptureStore


def test_filesystem_store_uses_configured_root(tmp_path: Path, monkeypatch) -> None:
    configured = tmp_path / "captures"
    monkeypatch.setenv("RAW_CAPTURE_ROOT", str(configured))

    pointer = FilesystemRawCaptureStore().put("approved-source", "a" * 64, b"evidence")

    assert pointer == "raw/approved-source/aa/" + "a" * 64 + ".csv"
    assert (configured / pointer).read_bytes() == b"evidence"


def test_filesystem_store_has_a_container_safe_fallback(monkeypatch) -> None:
    monkeypatch.delenv("RAW_CAPTURE_ROOT", raising=False)

    assert FilesystemRawCaptureStore._default_root().name == "raw-captures"
