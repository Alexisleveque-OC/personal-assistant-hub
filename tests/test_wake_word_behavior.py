"""Mot-clé « Otis » côté PWA (wake_word.js) exécuté sous Node avec un faux détecteur Vosk.

Le détecteur est contrôlé par le test (`detectors[0].wake()`, `failStart(err)`), les toasts, le bip et la dictée
déclenchée sont enregistrés. Remplace les anciens tests qui lisaient le texte de handleLocalWake / handleWakeEngineFailure.
"""
from tests.js_helpers import js_source, run_node

FAKES = """
console.debug = () => {};
console.error = () => {};
const state = { wakeWordEnabled: true, wakeWordCustomVariants: [] };
const audioFocusManager = { isDucking: () => false, releaseAllDucking: () => { events.push("release-all"); } };
const events = [];
const toasts = [];
const showToastError = (message) => toasts.push(["error", message]);
const showToastInfo = (message) => toasts.push(["info", message]);
const voiceDiagLog = { record: () => {} };
const timers = new Map();
let timerId = 0;
globalThis.setTimeout = (fn, ms) => { timers.set(++timerId, { fn, ms }); return timerId; };
globalThis.clearTimeout = (id) => timers.delete(id);
const fireTimers = (ms) => { for (const [id, t] of [...timers]) if (t.ms === ms) { timers.delete(id); t.fn(); } };
const detectors = [];
let startOutcome = null;
class VoskWakeWordDetector {
  constructor({ onWake }) { this.onWake = onWake; this.isRunning = false; detectors.push(this); }
  start() { return new Promise((resolve, reject) => { startOutcome = { resolve, reject }; }); }
  stop() { this.isRunning = false; events.push("detector-stop"); }
  wake() { this.onWake("otis"); }
}
const storage = {};
globalThis.localStorage = { setItem: (k, v) => { storage[k] = v; } };
const elements = { "wake-word-switch": { checked: true }, "wake-word-toggle": { checked: true } };
globalThis.document = { hidden: false, getElementById: (id) => elements[id] || null, addEventListener: () => {} };
globalThis.window = { AudioContext: class {
  constructor() { this.state = "running"; this.currentTime = 0; this.destination = {}; }
  createOscillator() { const ramp = { setValueAtTime() {}, exponentialRampToValueAtTime() {} };
    return { frequency: ramp, connect() {}, start() { events.push("chime"); }, stop() {} }; }
  createGain() { return { gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() {} }; }
  close() {}
} };
const flush = () => new Promise((resolve) => setImmediate(resolve));
const print = (value) => console.log(JSON.stringify(value));
"""


def _run(snippet: str):
    return run_node(FAKES + js_source("wake_word.js", strip_imports=True) + "\n" + snippet)


def test_local_wake_plays_the_chime_then_starts_the_dictation():
    out = _run("""
const wakes = [];
registerWakeCapture({ onWake: (text) => { events.push("dictation"); wakes.push(text); }, isBusy: () => false });
startWakeWordDetection();
detectors[0].wake();
print({ events, wakes });
""")

    assert out["events"] == ["chime", "dictation"]
    assert out["wakes"] == [""]  # la commande est dite après le bip


def test_engine_failure_shows_an_explicit_toast_and_disables_hands_free():
    out = _run("""
startWakeWordDetection();
startOutcome.reject(new Error("modèle introuvable"));
await flush();
print({ toasts, enabled: state.wakeWordEnabled, stored: storage.pah_wake_word_enabled,
        switchChecked: elements["wake-word-switch"].checked, toggleChecked: elements["wake-word-toggle"].checked, events });
""")

    assert out["toasts"] == [["error", "Détection locale du mot-clé indisponible : modèle introuvable. "
                                       "Mains-libres désactivé, le bouton micro reste utilisable."]]
    assert out["enabled"] is False and out["stored"] == "false"
    assert out["switchChecked"] is False and out["toggleChecked"] is False
    assert "release-all" in out["events"]


def test_first_model_download_is_announced_only_when_slow():
    out = _run("""
startWakeWordDetection();
fireTimers(2000);
const slow = toasts.slice();
startOutcome.resolve();
await flush();
print({ slow, pending: [...timers.values()].map((t) => t.ms) });
""")

    assert out["slow"] == [["info", "Préparation du mot-clé « Otis » : téléchargement du modèle (≈ 45 Mo, une seule fois)…"]]
    assert 2000 not in out["pending"]


def test_detection_does_not_start_while_paused_busy_or_hidden():
    out = _run("""
let busy = true;
registerWakeCapture({ onWake: () => {}, isBusy: () => busy });
startWakeWordDetection();
const whileBusy = detectors.length;
busy = false;
pauseWakeWordDetector();
startWakeWordDetection();
const whilePaused = detectors.length;
document.hidden = true;
resumeWakeWordDetector();
const whileHidden = detectors.length;
document.hidden = false;
resumeWakeWordDetector();
print({ whileBusy, whilePaused, whileHidden, resumed: detectors.length });
""")

    assert out == {"whileBusy": 0, "whilePaused": 0, "whileHidden": 0, "resumed": 1}


def test_phonetic_and_saved_variants_wake_otis_and_the_trailing_command_is_extracted():
    out = _run("""
state.wakeWordCustomVariants = ["oti"];
print({
  matches: ["Dis Otis", "autiste", "la notice", "oti", "bonjour"].map(isWakeWordMatch),
  command: extractCommandAfterWakeWord("Dis Otis, ajoute du lait"),
  none: extractCommandAfterWakeWord("ajoute du lait"),
});
""")

    assert out == {"matches": [True, True, True, True, False], "command": "ajoute du lait", "none": ""}
