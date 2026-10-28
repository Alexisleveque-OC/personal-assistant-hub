"""Route du modèle Vosk : envoyé en flux (chunked) car Cloud Run refuse les réponses HTTP/1 > 32 Mio (erreur 500)."""
from pathlib import Path

from fastapi.testclient import TestClient

import app.routers.wake_word as wake_word_router
from app.main import app

client = TestClient(app)

ROOT = Path(__file__).resolve().parent.parent


def test_model_is_streamed_without_content_length(tmp_path, monkeypatch):
    model = tmp_path / "model.tar.gz"
    payload = b"\x1f\x8b" + b"x" * (3 * 1024 * 1024)
    model.write_bytes(payload)
    monkeypatch.setattr(wake_word_router, "MODEL_PATH", model)

    res = client.get("/vosk/model.tar.gz?v=test")

    assert res.status_code == 200
    assert res.content == payload
    assert "content-length" not in res.headers
    assert res.headers["content-type"] == "application/gzip"
    assert "immutable" in res.headers["cache-control"]


def test_missing_model_fails_with_the_command_to_run(tmp_path, monkeypatch):
    monkeypatch.setattr(wake_word_router, "MODEL_PATH", tmp_path / "absent.tar.gz")

    res = client.get("/vosk/model.tar.gz")

    assert res.status_code == 404
    assert "scripts/fetch_vosk_assets.py" in res.json()["detail"]


def test_detector_downloads_the_model_from_the_streaming_route():
    module = client.get("/static/js/wake_word_vosk.js").text
    assert '"/vosk/model.tar.gz?v=' in module
    assert "/static/vendor/vosk/model.tar.gz" not in module


def test_service_worker_lets_the_model_download_bypass_its_cache():
    sw = (ROOT / "app" / "static" / "sw.js").read_text(encoding="utf-8")
    assert 'url.pathname.startsWith("/vosk/")' in sw
    assert sw.index('url.pathname.startsWith("/vosk/")') < sw.index("Stale-While-Revalidate")
    assert "pah-pwa-cache-v25" in sw
