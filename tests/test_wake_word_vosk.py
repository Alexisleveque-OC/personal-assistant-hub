"""Moteur local du mot-clé « Otis » via Vosk (Étape 3) : micro brut, grammaire restreinte, échecs explicites."""
import json
import mimetypes
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from scripts.fetch_vosk_assets import ASSETS_VERSION
from tests.js_helpers import run_node

client = TestClient(app)

MODULE_PATH = Path(__file__).resolve().parent.parent / "app" / "static" / "js" / "wake_word_vosk.js"


def _run_module_with(snippet: str) -> str:
    """Exécute le module ES réel sous Node (code envoyé sur stdin) suivi d'un extrait de test."""
    return run_node(MODULE_PATH.read_text(encoding="utf-8") + "\n" + snippet, parse_json=False)


def _module() -> str:
    res = client.get("/static/js/wake_word_vosk.js")
    assert res.status_code == 200
    assert "javascript" in res.headers.get("content-type", "")
    return res.text


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
const micConstraints = [];
let pendingMicrophone = null;
Object.defineProperty(globalThis, "navigator", { configurable: true, value: { mediaDevices: {
  getUserMedia: (constraints) => new Promise((resolve) => { micConstraints.push(constraints); pendingMicrophone = resolve; }),
} } });
function grantMicrophone() {
  const track = { stopped: false, stop() { this.stopped = true; } };
  tracks.push(track);
  pendingMicrophone({ getTracks: () => [track] });
}
const contexts = [];
globalThis.AudioContext = class {
  constructor() { this.state = "running"; this.sampleRate = 48000; this.audioWorklet = { addModule: async () => {} }; contexts.push(this); }
  createMediaStreamSource() { return { connect() {} }; }
  close() { this.closed = true; }
};
globalThis.AudioWorkletNode = class { constructor() { this.port = {}; } };
const handlers = {};
let recognizersCreated = 0;
let recognizerArgs = null;
let recognizersRemoved = 0;
const fakeClient = { KaldiRecognizer: class {
  constructor(...args) { recognizersCreated += 1; recognizerArgs = args; }
  on(event, listener) { handlers[event] = listener; }
  setWords() {}
  remove() { recognizersRemoved += 1; }
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


def test_listening_uses_a_raw_microphone_and_final_results_of_a_wake_word_grammar():
    """Micro brut : la musique n'est pas touchée. Résultats finaux seulement : les partiels déclenchent sur « les hôtes »."""
    snippet = BROWSER_FAKES + """
const starting = detector.start();
await tick();
grantMicrophone();
await starting;
console.log(JSON.stringify({ micConstraints, recognizerArgs, events: Object.keys(handlers).sort() }));
"""
    result = json.loads(_run_module_with(snippet))
    assert result["micConstraints"] == [{"audio": {"echoCancellation": False, "noiseSuppression": False,
                                                   "autoGainControl": False, "channelCount": 1}}]
    assert result["recognizerArgs"] == [48000, '["otis","[unk]"]']
    assert result["events"] == ["error", "result"]


def test_stop_releases_the_microphone_the_audio_context_and_the_recognizer():
    snippet = BROWSER_FAKES + """
const starting = detector.start();
await tick();
grantMicrophone();
await starting;
detector.stop();
console.log(JSON.stringify({ running: detector.isRunning, released: tracks[0].stopped,
                             closed: !!contexts[0].closed, recognizersRemoved }));
"""
    assert json.loads(_run_module_with(snippet)) == {"running": False, "released": True, "closed": True,
                                                     "recognizersRemoved": 1}


ENGINE_FAKES = """
const timers = new Map();
let timerId = 0;
globalThis.setTimeout = (fn, ms) => { timers.set(++timerId, { fn, ms }); return timerId; };
globalThis.clearTimeout = (id) => timers.delete(id);
globalThis.setInterval = () => 0;
globalThis.clearInterval = () => {};
let clientOptions = null;
let engineHandlers = {};
let importFails = false;
const fakeImport = async (url) => {
  if (importFails) throw new Error(`introuvable : ${url}`);
  return { VoskClient: class {
    constructor(options) { clientOptions = options; this.worker = { addEventListener() {} }; }
    on(event, listener) { engineHandlers[event] = listener; }
  } };
};
const flush = () => new Promise((resolve) => setImmediate(resolve));
const failureOf = async (outcome) => {
  const detector = new VoskWakeWordDetector({ onWake() {} });
  const starting = detector.start().then(() => null, (err) => `${err.name}: ${err.message}`);
  await flush();
  outcome();
  return starting;
};
"""


def test_engine_loads_the_vendored_assets_and_fails_explicitly():
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert source.count("await import(VOSK_CLIENT_URL)") == 1
    source = source.replace("await import(VOSK_CLIENT_URL)", "await fakeImport(VOSK_CLIENT_URL)")
    snippet = ENGINE_FAKES + source + """
const workerError = await failureOf(() => engineHandlers.error({ error: "mémoire saturée" }));
const options = clientOptions;
const timeout = await failureOf(() => [...timers.values()].find((t) => t.ms === LOAD_TIMEOUT_MS).fn());
importFails = true;
const missing = await failureOf(() => {});
console.log(JSON.stringify({ options, workerError, timeout, missing }));
"""
    result = json.loads(run_node(snippet, parse_json=False))
    assert result["options"]["workerUrl"] == "/static/vendor/vosk/vosk.worker.js"
    assert result["options"]["wasmUrl"] == "/static/vendor/vosk/vosk.wasm"
    assert result["options"]["modelUrl"] == f"/vosk/model.tar.gz?v={ASSETS_VERSION}"
    assert result["workerError"] == "WakeWordLoadError: Erreur du moteur Vosk : mémoire saturée"
    assert result["timeout"].startswith("WakeWordLoadError: Chargement du modèle Vosk trop long (> 120 s")
    assert result["missing"].startswith("WakeWordLoadError: Moteur Vosk introuvable (/static/vendor/vosk/vosk.wasm.js)")
