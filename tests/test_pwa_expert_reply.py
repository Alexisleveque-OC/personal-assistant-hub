"""PWA : lien discret « Approfondir » sous une réponse de l'expert, bouton pause de la voix (Phase 6.10, étape 4)."""
from tests.js_helpers import js_source, run_node

PRINT = "const print = (value) => console.log(JSON.stringify(value));\n"


def test_only_a_short_expert_answer_can_be_deepened():
    out = run_node(PRINT + js_source("expert_reply.js") + """
print({
  expert: canDeepen({ data: { level: "expert", expert: { reason: "demande" } } }),
  detailed: canDeepen({ data: { level: "expert", expert: { reason: "approfondir" } } }),
  agent: canDeepen({ data: { level: "agent" } }),
  empty: canDeepen({}),
  query: DEEPEN_QUERY,
  context: deepenContext(),
});
""")
    assert out == {"expert": True, "detailed": False, "agent": False, "empty": False,
                   "query": "Approfondis", "context": {"expert_detailed": True}}


STOP_FAKES = """
const listeners = {};
globalThis.window = { addEventListener: (type, fn) => { listeners[type] = fn; } };
const button = { hidden: true, onClick: null, addEventListener(type, fn) { this.onClick = fn; } };
"""


def test_pause_button_is_shown_while_otis_speaks_and_stops_the_voice():
    out = run_node(PRINT + STOP_FAKES + js_source("tts_stop.js") + """
let stopped = 0;
initTtsStop(button, () => { stopped += 1; });
const before = button.hidden;
listeners["tts-state"]({ detail: { speaking: true } });
const speaking = button.hidden;
button.onClick();
listeners["tts-state"]({ detail: { speaking: false } });
print({ before, speaking, stopped, after: button.hidden });
""")
    assert out == {"before": True, "speaking": False, "stopped": 1, "after": True}


def test_missing_pause_button_is_reported_not_thrown():
    out = run_node(PRINT + STOP_FAKES + "console.warn = (m) => print({ warned: String(m) });\n" + js_source("tts_stop.js") + """
initTtsStop(null, () => {});
""")
    assert "btn-tts-stop" in out["warned"]


TTS_FAKES = """
const events = [];
globalThis.window = { dispatchEvent: (e) => events.push(e.detail.speaking), speechSynthesis: {
  cancel() {}, speak(u) { this.last = u; },
} };
globalThis.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init.detail; } };
globalThis.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
globalThis.setTimeout = () => 1;
globalThis.clearTimeout = () => {};
const state = { ttsEnabled: true, selectedVoiceUri: null };
const audioFocusManager = { requestDucking() {}, releaseDucking() {} };
const pauseWakeWordDetector = () => {};
const resumeWakeWordDetector = () => {};
"""


def test_speech_announces_when_it_starts_and_when_it_is_cut():
    out = run_node(PRINT + TTS_FAKES + js_source("tts.js", strip_imports=True) + """
speak("Bonjour");
const beforeStart = [...events];
window.speechSynthesis.last.onstart();
cancelSpeaking();
print({ beforeStart, events });
""")
    assert out["events"][-2:] == [True, False]
