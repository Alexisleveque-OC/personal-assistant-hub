"""Capture micro (mic_capture.js) exécutée sous Node dans un faux navigateur.

Micro à ouverture contrôlée (`openMic`), MediaRecorder et AudioContext simulés, horloge (`now`) et minuteurs manuels
(`fireTimers(ms)`), niveau sonore injecté image par image (`tick(level)`). Les imports du module sont remplacés par
des doublures ; le journal du micro (`log`) sert d'observable.
Remplace les anciens tests qui lisaient le texte du module (bouton hybride du 04/11, garde de double capture).
"""
from tests.js_helpers import js_source, run_node

FAKE_BROWSER = """
console.debug = () => {};  // sous Node, console.debug écrit sur stdout (réservé au JSON du test)
const state = { pushToTalk: true, vadSilenceMs: 2000, wakeWordEnabled: false };
const log = [];
const toasts = [];
const audioFocusManager = { requestDucking: () => {}, releaseDucking: () => {} };
const showToastInfo = (message) => toasts.push(message);
const voiceDiagLog = { record: (_channel, message) => log.push(message) };
const extractCommandAfterWakeWord = () => "";
const pauseWakeWordDetector = () => {};
const resumeWakeWordDetector = () => {};
const registerWakeCapture = () => {};
const startWakeWordDetection = () => {};

let now = 0;
Object.defineProperty(globalThis, "performance", { value: { now: () => now }, configurable: true });
const timers = new Map();
let timerId = 0;
globalThis.setTimeout = (fn, ms) => { timers.set(++timerId, { fn, ms }); return timerId; };
globalThis.clearTimeout = (id) => timers.delete(id);
const fireTimers = (ms) => { for (const [id, t] of [...timers]) if (t.ms === ms) { timers.delete(id); t.fn(); } };
let frame = null;
globalThis.requestAnimationFrame = (fn) => { frame = fn; return 1; };
globalThis.cancelAnimationFrame = () => { frame = null; };
let level = 0;
const tick = (value) => { level = value; const f = frame; frame = null; if (f) f(); };

class FakeEl {
  constructor(id) {
    this.id = id; this.listeners = {}; this.style = {}; this.textContent = ""; this.classes = new Set();
    this.classList = {
      toggle: (c, on) => (on ? this.classes.add(c) : this.classes.delete(c)),
      add: (c) => this.classes.add(c), remove: (c) => this.classes.delete(c),
    };
    this.parentNode = { replaceChild: (node, old) => { els[old.id] = node; } };
  }
  cloneNode() { return new FakeEl(this.id); }
  addEventListener(type, fn) { this.listeners[type] = fn; }
  setPointerCapture() {}
  hasPointerCapture() { return false; }
}
const els = { "mic-btn": new FakeEl("mic-btn"), "mic-wrapper": new FakeEl("mic-wrapper") };
const windowListeners = {};

const recorders = [];
class FakeMediaRecorder {
  static isTypeSupported(type) { return type === "audio/webm;codecs=opus"; }
  constructor(_stream, options) { this.state = "inactive"; this.mimeType = options.mimeType; recorders.push(this); }
  start() { this.state = "recording"; }
  stop() { this.state = "inactive"; this.onstop(); }
}
class FakeAudioContext {
  constructor() { this.state = "running"; }
  createMediaStreamSource() { return { connect() {} }; }
  createAnalyser() { return { frequencyBinCount: 4, getByteFrequencyData: (data) => data.fill(level) }; }
  close() { this.state = "closed"; }
}
globalThis.MediaRecorder = FakeMediaRecorder;
globalThis.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init && init.detail; } };
globalThis.window = {
  MediaRecorder: FakeMediaRecorder, AudioContext: FakeAudioContext, dispatchEvent: () => {},
  addEventListener: (type, fn) => (windowListeners[type] ||= new Set()).add(fn),
  removeEventListener: (type, fn) => windowListeners[type] && windowListeners[type].delete(fn),
};
globalThis.document = { getElementById: (id) => els[id] || null, querySelectorAll: () => [] };
const micRequests = [];
Object.defineProperty(globalThis, "navigator", {
  value: { mediaDevices: { getUserMedia: () => new Promise((resolve, reject) => micRequests.push({ resolve, reject })) } },
  configurable: true,
});
"""

SETUP = """
const sent = [];
let notAllowed = 0;
initSpeechRecognition(() => {}, () => { notAllowed += 1; }, (blob) => sent.push(blob.size));
const flush = () => new Promise((resolve) => setImmediate(resolve));
const stream = { getTracks: () => [{ stop() {} }] };
const openMic = async () => { micRequests.shift().resolve(stream); await flush(); };
const press = () => els["mic-btn"].listeners.pointerdown({ preventDefault() {}, pointerId: 1 });
const release = (afterMs) => { now += afterMs; windowListeners.pointerup.forEach((fn) => fn({ pointerId: 1 })); };
const speak = (bytes) => recorders[recorders.length - 1].ondataavailable({ data: new Blob(["x".repeat(bytes)]) });
const stops = () => log.map((m) => (m.match(/^Arrêt \\((.+?)\\) après/) || [])[1]).filter(Boolean);
const print = (value) => console.log(JSON.stringify(value));
"""


def _run(snippet: str):
    return run_node(FAKE_BROWSER + js_source("mic_capture.js", strip_imports=True) + SETUP + snippet)


def test_short_press_is_a_tap_and_long_press_is_a_hold():
    out = _run("print([isHoldRelease(120), isHoldRelease(399), isHoldRelease(400), isHoldRelease(2500), HOLD_THRESHOLD_MS]);")
    assert out == [False, False, True, True, 400]


def test_a_capture_already_starting_is_never_started_twice():
    out = _run("""
state.pushToTalk = false;
setupMicButtonBehavior();
els["mic-btn"].listeners.click();
els["mic-btn"].listeners.click();  // micro encore en cours d'ouverture
const onceWhileStarting = captureOnce(() => {});
print({ requests: micRequests.length, ignored: log.filter((m) => m.startsWith("Démarrage ignoré")).length,
        onceWhileStarting, toasts });
""")

    assert out["requests"] == 1 and out["ignored"] == 1
    assert out["onceWhileStarting"] is False and out["toasts"] == ["Une dictée est déjà en cours."]


def test_a_release_while_the_microphone_opens_is_applied_once_open():
    out = _run("""
press();
release(500);  // appui long relâché avant l'ouverture du micro
const deferred = log.some((m) => m.includes("demandé pendant l'ouverture du micro"));
await openMic();
print({ deferred, stops: stops(), recorder: recorders[0].state });
""")

    assert out == {"deferred": True, "stops": ["relâché"], "recorder": "inactive"}


def test_push_to_talk_tap_toggles_and_hold_stops_on_release():
    out = _run("""
press();
await openMic();
release(150);  // appui bref : bascule, la capture continue
const afterTap = stops().length;
press();  // toucher suivant : arrêt
press();
await openMic();
release(1200);  // appui long : arrêt au relâchement
print({ afterTap, stops: stops() });
""")

    assert out == {"afterTap": 0, "stops": ["bouton", "relâché"]}


def test_window_release_listeners_are_replaced_not_accumulated():
    out = _run("""
setupMicButtonBehavior();
setupMicButtonBehavior();
print([windowListeners.pointerup.size, windowListeners.pointercancel.size]);
""")
    assert out == [1, 1]


def test_silence_never_cuts_a_held_press_but_stops_a_tap():
    out = _run("""
press();
await openMic();
tick(50); tick(0);  // parole puis pause
fireTimers(2000); fireTimers(7000);
const whileHeld = stops().length;
release(3000);
press();
await openMic();
release(100);  // appui bref : le silence arrête la capture
tick(50); tick(0);
fireTimers(2000);
print({ whileHeld, stops: stops() });
""")

    assert out == {"whileHeld": 0, "stops": ["relâché", "silence"]}


def test_recordings_go_to_otis_or_to_a_one_shot_target_and_short_ones_are_announced():
    out = _run("""
const dictated = [];
press(); await openMic(); release(100); speak(2000); press();
const once = captureOnce((blob) => dictated.push(blob.size));
await openMic(); speak(3000); press();
press(); await openMic(); release(100); speak(10); press();
captureOnce(() => dictated.push("jamais"));
micRequests.shift().reject(new Error("refus"));
await flush();
press(); await openMic(); release(100); speak(1500); press();
print({ sent, dictated, once, toasts, notAllowed });
""")

    assert out["once"] is True
    assert out["dictated"] == [3000]  # la capture à usage unique ne part pas vers Otis
    assert out["sent"] == [2000, 1500]  # après un refus du micro, la dictée suivante repart vers Otis
    assert out["toasts"] == ["Message trop court : rien n'a été envoyé."]
    assert out["notAllowed"] == 1
