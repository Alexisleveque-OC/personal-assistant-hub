"""E2E (ROADMAP Étape 3) : une réponse d'Otis baisse la musique via le clip porteur puis la laisse remonter."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

SPEECH_PATH = Path(__file__).resolve().parent.parent / "app" / "static" / "js" / "speech.js"
WINDOWS_NODE = Path("/mnt/c/Program Files/nodejs/node.exe")
NODE = shutil.which("node") or (str(WINDOWS_NODE) if WINDOWS_NODE.exists() else None)

# Navigateur simulé : la synthèse vocale et la balise <audio> journalisent dans le même ordre que sur le téléphone.
OTIS_REPLY_FLOW = """
const events = [];
const storage = {};
globalThis.window = globalThis;
globalThis.localStorage = {
  getItem: (key) => storage[key] ?? null,
  setItem: (key, value) => { storage[key] = String(value); },
  removeItem: (key) => { delete storage[key]; },
};
globalThis.document = {
  hidden: false,
  getElementById: () => null,
  querySelectorAll: () => [],
  addEventListener: () => {},
};
globalThis.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init.detail; } };
globalThis.dispatchEvent = (event) => events.push(`${event.type} ${event.detail.reason}`);
URL.createObjectURL = (blob) => `blob:${blob.type}`;
globalThis.Audio = class {
  constructor() { this.attributes = {}; }
  set src(value) { this.attributes.src = value; }
  getAttribute(name) { return this.attributes[name] ?? null; }
  removeAttribute(name) { delete this.attributes[name]; }
  play() { events.push(`audio play ${this.attributes.src} loop=${this.loop}`); return Promise.resolve(); }
  pause() { events.push("audio pause"); }
  load() { events.push("audio emptied"); }
};
let lastUtterance = null;
globalThis.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
globalThis.speechSynthesis = {
  getVoices: () => [],
  speak: (utterance) => { lastUtterance = utterance; events.push(`tts speak « ${utterance.text} »`); },
  cancel: () => events.push("tts cancel"),
};

const speech = await import(SPEECH_URL);
const { audioFocusManager } = await import(new URL("./audio_focus.js", SPEECH_URL).href);
const result = {};

// 1. Réponse complète : musique baissée avant la voix, remontée à la fin.
speech.speak("J'ai ajouté du lait.");
lastUtterance.onstart();
result.duckedWhileSpeaking = audioFocusManager.isDucking();
lastUtterance.onend();
result.reply = events.splice(0);
result.duckedAfterReply = audioFocusManager.isDucking();

// 2. Réponse interrompue (nouvelle dictée, bouton stop) : la musique remonte aussi.
speech.speak("Voici la liste de courses.");
lastUtterance.onstart();
events.length = 0;
speech.cancelSpeaking();
result.interrupted = events.splice(0);
result.duckedAfterInterrupt = audioFocusManager.isDucking();

console.log(JSON.stringify(result));
process.exit(0);
"""


def test_e2e_otis_reply_ducks_the_music_and_lets_it_come_back():
    if not NODE:
        pytest.skip("Node.js indisponible pour exécuter les modules JS")
    speech_url = SPEECH_PATH.as_uri()
    if NODE == str(WINDOWS_NODE):
        # Node Windows depuis WSL : chemin UNC \\wsl.localhost\... → file://wsl.localhost/...
        speech_url = "file:" + subprocess.run(["wslpath", "-m", str(SPEECH_PATH)], capture_output=True, text=True, check=True).stdout.strip()
    proc = subprocess.run(
        [NODE, "--input-type=module"],
        input=f"const SPEECH_URL = {json.dumps(speech_url)};\n" + OTIS_REPLY_FLOW, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout.strip().splitlines()[-1])

    assert result["reply"] == [
        # speak() annule d'abord toute réponse en cours (événement de fin émis même sans baisse active)
        "tts cancel",
        "pah-audio-ducking-end tts",
        "audio play blob:audio/wav loop=true",
        "pah-audio-ducking-start tts",
        "tts speak « J'ai ajouté du lait. »",
        "audio pause",
        "audio emptied",
        "pah-audio-ducking-end tts",
    ]
    assert result["duckedWhileSpeaking"] is True
    assert result["duckedAfterReply"] is False
    assert result["interrupted"] == ["tts cancel", "audio pause", "audio emptied", "pah-audio-ducking-end tts"]
    assert result["duckedAfterInterrupt"] is False


def test_e2e_application_serves_the_reply_ducking_chain():
    # 1. Module de focus audio : clip porteur vidé en fin de réponse
    focus = client.get("/static/js/audio_focus.js").text
    assert "startCarrier()" in focus and "stopCarrier()" in focus
    assert 'removeAttribute("src")' in focus

    # 2. La synthèse vocale passe par le gestionnaire de focus
    speech = client.get("/static/js/speech.js").text
    assert 'audioFocusManager.requestDucking("tts")' in speech
    assert 'audioFocusManager.releaseDucking("tts")' in speech

    # 3. Service worker : nouvelle version pour livrer le module modifié aux PWA installées
    sw = client.get("/sw.js").text
    assert "pah-pwa-cache-v25" in sw
    assets = re.search(r"ASSETS_TO_CACHE = \[(.*?)\];", sw, re.S).group(1)
    assert '"/static/js/audio_focus.js"' in assets
