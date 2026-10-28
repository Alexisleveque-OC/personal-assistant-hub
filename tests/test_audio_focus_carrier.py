"""Clip porteur (ROADMAP Étape 2) : une balise <audio> quasi silencieuse fait baisser la musique pendant qu'Otis parle (Chrome Android)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parent.parent / "app" / "static" / "js" / "audio_focus.js"
WINDOWS_NODE = Path("/mnt/c/Program Files/nodejs/node.exe")
NODE = shutil.which("node") or (str(WINDOWS_NODE) if WINDOWS_NODE.exists() else None)

# Fausse balise <audio> : journalise les appels qui prennent ou rendent le focus audio.
BROWSER_FAKES = """
const events = [];
const warnings = [];
let rejectNextPlay = false;
globalThis.URL.createObjectURL = (blob) => { events.push(`blob ${blob.type} ${blob.size}`); return "blob:carrier"; };
globalThis.Audio = class {
  constructor() { this.attributes = {}; this.loop = false; this.currentTime = 0; events.push("new Audio"); }
  set src(value) { this.attributes.src = value; }
  get src() { return this.attributes.src || ""; }
  getAttribute(name) { return this.attributes[name] ?? null; }
  removeAttribute(name) { delete this.attributes[name]; events.push(`removeAttribute ${name}`); }
  play() {
    events.push(`play ${this.src} loop=${this.loop}`);
    if (rejectNextPlay) { rejectNextPlay = false; return Promise.reject(new Error("NotAllowedError")); }
    return Promise.resolve();
  }
  pause() { events.push("pause"); }
  load() { events.push("load"); }
};
console.warn = (...args) => warnings.push(args.join(" "));
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
"""


def _run_module_with(snippet: str) -> dict:
    """Exécute le module ES réel sous Node (code envoyé sur stdin) et renvoie le JSON affiché par l'extrait."""
    if not NODE:
        pytest.skip("Node.js indisponible pour exécuter le module JS")
    source = BROWSER_FAKES + MODULE_PATH.read_text(encoding="utf-8") + "\n" + snippet
    result = subprocess.run([NODE, "--input-type=module"], input=source, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_tts_ducking_plays_a_looping_near_silent_wav_clip():
    result = _run_module_with("""
const manager = new AudioFocusManager();
manager.requestDucking("tts");
console.log(JSON.stringify({ events }));
""")
    # 1 s en 8 kHz mono 16 bits : 44 octets d'en-tête + 16 000 octets d'échantillons.
    assert result["events"] == ["blob audio/wav 16044", "new Audio", "play blob:carrier loop=true"]


def test_repeated_tts_ducking_keeps_a_single_playing_clip():
    result = _run_module_with("""
const manager = new AudioFocusManager();
manager.requestDucking("tts");
manager.requestDucking("tts");
console.log(JSON.stringify({ plays: events.filter((e) => e.startsWith("play")).length, audios: events.filter((e) => e === "new Audio").length }))
""")
    assert result == {"plays": 1, "audios": 1}


def test_tts_release_empties_the_audio_element_instead_of_only_pausing_it():
    """Mesuré sur le téléphone : une simple pause garde le focus (musique jamais remontée), vider la balise le rend."""
    result = _run_module_with("""
const manager = new AudioFocusManager();
manager.requestDucking("tts");
events.length = 0;
manager.releaseDucking("tts");
console.log(JSON.stringify({ events }));
""")
    assert result["events"] == ["pause", "removeAttribute src", "load"]


def test_next_reply_reuses_the_same_element_and_clip():
    result = _run_module_with("""
const manager = new AudioFocusManager();
manager.requestDucking("tts");
manager.releaseDucking("tts");
events.length = 0;
manager.requestDucking("tts");
console.log(JSON.stringify({ events }));
""")
    assert result["events"] == ["play blob:carrier loop=true"]


def test_release_without_a_reply_in_progress_does_nothing():
    result = _run_module_with("""
const manager = new AudioFocusManager();
manager.releaseDucking("tts");
console.log(JSON.stringify({ events }));
""")
    assert result["events"] == []


def test_recording_does_not_play_the_clip():
    result = _run_module_with("""
const manager = new AudioFocusManager();
manager.requestDucking("recording");
manager.releaseDucking("recording");
console.log(JSON.stringify({ events }));
""")
    assert result["events"] == []


def test_releasing_all_ducking_empties_the_clip():
    result = _run_module_with("""
const manager = new AudioFocusManager();
manager.requestDucking("tts");
manager.requestDucking("recording");
events.length = 0;
manager.releaseAllDucking();
console.log(JSON.stringify({ events, ducking: manager.isDucking() }));
""")
    assert result == {"events": ["pause", "removeAttribute src", "load"], "ducking": False}


def test_tts_release_while_recording_still_empties_the_clip():
    result = _run_module_with("""
const manager = new AudioFocusManager();
manager.requestDucking("tts");
manager.requestDucking("recording");
events.length = 0;
manager.releaseDucking("tts");
console.log(JSON.stringify({ events }));
""")
    assert result["events"] == ["pause", "removeAttribute src", "load"]


def test_a_refused_playback_is_reported_explicitly():
    result = _run_module_with("""
const manager = new AudioFocusManager();
rejectNextPlay = true;
manager.requestDucking("tts");
await tick();
console.log(JSON.stringify({ warnings, ducking: manager.isDucking() }));
""")
    assert result["ducking"] is True
    assert len(result["warnings"]) == 1
    assert "[AudioFocus]" in result["warnings"][0] and "NotAllowedError" in result["warnings"][0]
