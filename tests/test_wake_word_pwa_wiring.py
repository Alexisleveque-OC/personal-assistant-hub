"""Branchement de la détection locale Vosk dans la PWA (Étape 4) : plus de Web Speech continue pour le mot-clé."""
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"


def _voice_js() -> str:
    return client.get("/static/js/wake_word.js").text + client.get("/static/js/mic_capture.js").text


def test_wake_word_listening_uses_the_local_vosk_detector():
    content = _voice_js()
    assert 'import { VoskWakeWordDetector } from "./wake_word_vosk.js"' in content
    assert "new VoskWakeWordDetector(" in content


def test_continuous_web_speech_no_longer_listens_for_the_wake_word():
    """Chrome Android relance la Web Speech API toutes les ~5 s et coupe la musique à chaque relance."""
    content = _voice_js()
    assert "continuous = true" not in content
    assert "wakeRecInstance" not in content


def test_local_wake_triggers_the_chime_then_the_dictation():
    content = _voice_js()
    handler = content[content.index("function handleLocalWake"):]
    handler = handler[: handler.index("\n}\n")]
    assert "playWakeChime()" in handler
    assert "triggerWakeCapture(" in handler


def test_engine_failure_shows_an_explicit_toast_and_disables_hands_free():
    content = _voice_js()
    failure = content[content.index("function handleWakeEngineFailure"):]
    failure = failure[: failure.index("\n}\n")]
    assert "showToastError(" in failure
    assert "Mains-libres désactivé" in failure
    assert "setWakeWordEnabled(false)" in failure


def test_first_model_download_is_announced():
    assert "45 Mo" in _voice_js()


def test_hands_free_toast_no_longer_warns_about_the_music():
    app_js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "peut baisser la musique" not in app_js
