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


def test_audio_diag_page_exposes_the_five_modes():
    html = client.get("/static/audio_diag.html").text
    for mode in ("speech-continuous", "speech-single", "gum-processing", "gum-raw", "gum-raw-analyser"):
        assert f'data-mode="{mode}"' in html


def test_audio_diag_raw_modes_disable_every_audio_processing():
    html = client.get("/static/audio_diag.html").text
    assert "echoCancellation: false" in html
    assert "noiseSuppression: false" in html
    assert "autoGainControl: false" in html
    assert "echoCancellation: true" in html


def test_audio_diag_page_reports_effective_track_settings_and_level():
    html = client.get("/static/audio_diag.html").text
    assert "getSettings()" in html
    assert "AnalyserNode" in html or "createAnalyser" in html
    assert 'id="diag-log"' in html


def test_audio_diag_page_stays_out_of_the_pwa_cache():
    assert "audio_diag" not in SW_PATH.read_text(encoding="utf-8")
    assert "audio_diag" not in client.get("/app").text


def test_audio_diag_page_exposes_the_otis_reply_modes():
    html = client.get("/static/audio_diag.html").text
    for mode in ("tts-only", "tts-mic-processed", "tts-audio-element"):
        assert f'data-mode="{mode}"' in html


def test_audio_diag_otis_reply_modes_speak_in_french_and_log_synthesis_events():
    html = client.get("/static/audio_diag.html").text
    assert "new SpeechSynthesisUtterance(" in html
    assert 'utterance.lang = "fr-FR"' in html
    assert "utterance.onstart" in html and "utterance.onend" in html and "utterance.onerror" in html
    assert "speechSynthesis.cancel()" in html


def test_audio_diag_tts_with_audio_element_plays_a_generated_clip_through_an_audio_tag():
    html = client.get("/static/audio_diag.html").text
    assert "new Audio(" in html
    assert "audio/wav" in html
    assert 'id="carrier-duration"' in html
