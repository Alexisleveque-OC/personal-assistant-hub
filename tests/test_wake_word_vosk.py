"""Moteur local du mot-clé « Otis » via Vosk (Étape 3) : micro brut, grammaire restreinte, échecs explicites."""
import json
import mimetypes
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from scripts.fetch_vosk_assets import ASSETS_VERSION

client = TestClient(app)

MODULE_PATH = Path(__file__).resolve().parent.parent / "app" / "static" / "js" / "wake_word_vosk.js"
WINDOWS_NODE = Path("/mnt/c/Program Files/nodejs/node.exe")
NODE = shutil.which("node") or (str(WINDOWS_NODE) if WINDOWS_NODE.exists() else None)


def _run_module_with(snippet: str) -> str:
    """Exécute le module ES réel sous Node (code envoyé sur stdin) suivi d'un extrait de test."""
    if not NODE:
        pytest.skip("Node.js indisponible pour exécuter le module JS")
    source = MODULE_PATH.read_text(encoding="utf-8") + "\n" + snippet
    result = subprocess.run([NODE, "--input-type=module"], input=source, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return result.stdout


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


def test_wake_word_must_be_the_last_word_before_the_pause():
    """Mesuré en navigateur : « les hôtes sont arrivés » donne « otis [unk] » ; un vrai « Otis » est suivi de la pause."""
    cases = {
        "otis": True,
        "[unk] otis": True,
        "[unk] [unk] otis": True,
        "OTIS": True,
        "otis [unk]": False,
        "[unk] otis [unk]": False,
        "[unk]": False,
        "": False,
    }
    snippet = f"const cases = {json.dumps(list(cases))};\n"
    snippet += "console.log(JSON.stringify(cases.map((t) => transcriptHasWakeWord(t)).concat([transcriptHasWakeWord(null)])));"
    assert json.loads(_run_module_with(snippet)) == [*cases.values(), False]


def test_model_url_is_versioned_with_the_fetched_assets_to_refresh_the_browser_cache():
    assert f"/vosk/model.tar.gz?v={ASSETS_VERSION}" in _module()


def test_module_loads_vendored_assets_and_fails_fast_on_timeout_or_worker_error():
    content = _module()
    assert "/static/vendor/vosk/vosk.wasm.js" in content
    assert "/static/vendor/vosk/vosk.worker.js" in content
    assert "/static/vendor/vosk/vosk.wasm" in content
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


BROWSER_FAKES = """
const tracks = [];
let pendingMicrophone = null;
Object.defineProperty(globalThis, "navigator", { configurable: true, value: { mediaDevices: {
  getUserMedia: () => new Promise((resolve) => { pendingMicrophone = resolve; }),
} } });
function grantMicrophone() {
  const track = { stopped: false, stop() { this.stopped = true; } };
  tracks.push(track);
  pendingMicrophone({ getTracks: () => [track] });
}
globalThis.AudioContext = class {
  constructor() { this.state = "running"; this.sampleRate = 48000; this.audioWorklet = { addModule: async () => {} }; }
  createMediaStreamSource() { return { connect() {} }; }
  close() { this.closed = true; }
};
globalThis.AudioWorkletNode = class { constructor() { this.port = {}; } };
const handlers = {};
let recognizersCreated = 0;
const fakeClient = { KaldiRecognizer: class {
  constructor() { recognizersCreated += 1; }
  on(event, listener) { handlers[event] = listener; }
  setWords() {}
  remove() {}
} };
const logs = [];
const wakes = [];
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
const detector = new VoskWakeWordDetector({
  onWake: (text) => wakes.push(text),
  log: (message) => logs.push(message),
  loadClient: async () => fakeClient,
});
"""


def test_stop_during_start_releases_the_late_microphone_without_raising():
    snippet = BROWSER_FAKES + """
const starting = detector.start();
await tick();
detector.stop();
grantMicrophone();
await starting;
console.log(JSON.stringify({ running: detector.isRunning, released: tracks[0].stopped, recognizersCreated }));
"""
    assert json.loads(_run_module_with(snippet)) == {"running": False, "released": True, "recognizersCreated": 0}


def test_wake_logs_confidence_and_duration_and_ignored_candidates_are_logged():
    snippet = BROWSER_FAKES + """
const starting = detector.start();
await tick();
grantMicrophone();
await starting;
handlers.result({ result: { text: "otis [unk]", result: [
  { word: "otis", conf: 0.73, start: 1.0, end: 1.21 }, { word: "[unk]", conf: 1, start: 1.21, end: 1.8 },
] } });
handlers.result({ result: { text: "otis", result: [{ word: "otis", conf: 1, start: 4.0, end: 4.55 }] } });
console.log(JSON.stringify({ wakes, running: detector.isRunning, released: tracks[0].stopped, logs }));
"""
    result = json.loads(_run_module_with(snippet))
    assert result["wakes"] == ["otis"]
    assert result["running"] is False
    assert result["released"] is True
    assert any("ignoré" in line and "otis [unk]" in line and "0.73" in line for line in result["logs"])
    assert any("détecté" in line and "confiance 1.00" in line and "durée 0.55 s" in line for line in result["logs"])


def test_wake_requires_a_confidence_of_at_least_0_95():
    """Mesuré sur le téléphone : vrais « Otis » à 1,00 ; « mes hôtes sont partis tôt » → « [unk] otis » à 0,90."""
    snippet = BROWSER_FAKES + """
const starting = detector.start();
await tick();
grantMicrophone();
await starting;
handlers.result({ result: { text: "[unk] otis", result: [
  { word: "[unk]", conf: 1, start: 0.2, end: 0.8 }, { word: "otis", conf: 0.90, start: 0.8, end: 1.04 },
] } });
const runningAfterLowConfidence = detector.isRunning;
handlers.result({ result: { text: "otis", result: [{ word: "otis", conf: 0.95, start: 3.0, end: 3.3 }] } });
console.log(JSON.stringify({ wakes, runningAfterLowConfidence, logs }));
"""
    result = json.loads(_run_module_with(snippet))
    assert result["wakes"] == ["otis"]
    assert result["runningAfterLowConfidence"] is True
    assert any("ignoré" in line and "0.90" in line for line in result["logs"])
