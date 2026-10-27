"""Moteur local du mot-clé « Otis » via Vosk (Étape 3) : micro brut, grammaire restreinte, échecs explicites."""
import mimetypes

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _module() -> str:
    res = client.get("/static/js/wake_word_vosk.js")
    assert res.status_code == 200
    assert "javascript" in res.headers.get("content-type", "")
    return res.text


def test_module_exposes_a_detector_and_an_explicit_load_error():
    content = _module()
    assert "export class VoskWakeWordDetector" in content
    assert "export class WakeWordLoadError" in content
    assert "export function transcriptHasWakeWord" in content


def test_module_uses_a_raw_microphone_to_keep_the_music_untouched():
    content = _module()
    assert "echoCancellation: false" in content
    assert "noiseSuppression: false" in content
    assert "autoGainControl: false" in content
    assert "echoCancellation: true" not in content


def test_module_restricts_recognition_to_the_wake_word():
    content = _module()
    assert '["otis", "[unk]"]' in content


def test_module_triggers_on_final_results_only_to_avoid_false_wakes():
    """Mesuré en navigateur : les résultats partiels déclenchent sur « les hôtes », les résultats finaux non."""
    content = _module()
    assert 'recognizer.on("result"' in content
    assert "partialresult" not in content


def test_module_loads_vendored_assets_and_fails_fast_on_timeout_or_worker_error():
    content = _module()
    assert "/static/vendor/vosk/vosk.wasm.js" in content
    assert "/static/vendor/vosk/vosk.worker.js" in content
    assert "/static/vendor/vosk/vosk.wasm" in content
    assert "/static/vendor/vosk/model.tar.gz" in content
    assert "LOAD_TIMEOUT_MS" in content
    assert 'on("error"' in content


def test_module_releases_the_microphone_on_stop():
    content = _module()
    assert "stop()" in content
    assert "getTracks().forEach" in content
    assert ".close()" in content


def test_capture_worklet_is_served_and_registered():
    res = client.get("/static/js/vosk_capture_worklet.js")
    assert res.status_code == 200
    assert "registerProcessor" in res.text
    assert "vosk_capture_worklet.js" in _module()


def test_wasm_files_are_served_with_the_wasm_mime_type():
    assert mimetypes.guess_type("vosk.wasm")[0] == "application/wasm"


def test_diag_page_offers_a_vosk_wake_word_mode():
    html = client.get("/static/audio_diag.html").text
    assert 'data-mode="vosk-wake"' in html
    assert "wake_word_vosk.js" in html
