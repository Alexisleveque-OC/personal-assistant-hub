"""Page de diagnostic audio (Étape 0) : compare l'effet de chaque mode de capture micro sur la musique Android."""
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

SW_PATH = Path(__file__).resolve().parent.parent / "app" / "static" / "sw.js"


def test_audio_diag_page_is_served_as_html():
    res = client.get("/static/audio_diag.html")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")


def test_audio_diag_page_stays_out_of_the_pwa_cache():
    assert "audio_diag" not in SW_PATH.read_text(encoding="utf-8")
    assert "audio_diag" not in client.get("/app").text
