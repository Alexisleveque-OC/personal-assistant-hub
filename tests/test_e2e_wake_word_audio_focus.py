"""Test d'intégration End-to-End (E2E) de la feature « Mot-clé Otis sans couper la musique » (Étape 5).

Valide le flux de bout en bout :
1. Détecteur réel (module ES exécuté sous Node, navigateur simulé) sur un cycle complet :
   paroles de musique et « mes hôtes » ignorés, vrai « Otis » → réveil et micro libéré,
   reprise après la réponse d'Otis → second réveil. Micro toujours ouvert sans traitements audio.
2. Chaîne servie par l'application : page de diagnostic, modules, modèle en flux,
   service worker (pré-cache des modules, modèle hors cache), branchement « Otis » → bip → dictée,
   endpoint audio protégé par clé d'API.
"""
import json
import re

from fastapi.testclient import TestClient

import app.routers.wake_word as wake_word_router
from app.config import settings
from app.main import app
from tests.test_wake_word_vosk import BROWSER_FAKES, _run_module_with

client = TestClient(app)


def test_e2e_detector_full_cycle_with_music_trap_wake_and_resume():
    snippet = BROWSER_FAKES + """
const constraints = [];
const requestMicrophone = navigator.mediaDevices.getUserMedia;
navigator.mediaDevices.getUserMedia = (wanted) => { constraints.push(wanted.audio); return requestMicrophone(wanted); };
const word = (text, conf, start, end) => ({ word: text, conf, start, end });

async function listen() {
  const starting = detector.start();
  await tick();
  grantMicrophone();
  await starting;
}

await listen();
handlers.result({ result: { text: "[unk] otis [unk]", result: [
  word("[unk]", 1, 0, 0.5), word("otis", 0.84, 0.5, 0.85), word("[unk]", 1, 0.85, 2.0),
] } });
handlers.result({ result: { text: "[unk] otis", result: [word("[unk]", 1, 3, 3.6), word("otis", 0.90, 3.6, 3.84)] } });
const stillListeningAfterTraps = detector.isRunning;
handlers.result({ result: { text: "otis", result: [word("otis", 1, 6, 6.5)] } });
const releasedAfterWake = tracks[0].stopped;

await listen();
handlers.result({ result: { text: "otis", result: [word("otis", 1, 2, 2.4)] } });

console.log(JSON.stringify({
  wakes, stillListeningAfterTraps, releasedAfterWake,
  allReleased: tracks.every((t) => t.stopped), microphones: tracks.length, constraints,
}));
"""
    result = json.loads(_run_module_with(snippet))

    assert result["stillListeningAfterTraps"] is True
    assert result["wakes"] == ["otis", "otis"]
    assert result["releasedAfterWake"] is True
    assert result["allReleased"] is True
    assert result["microphones"] == 2
    for audio in result["constraints"]:
        assert audio["echoCancellation"] is False
        assert audio["noiseSuppression"] is False
        assert audio["autoGainControl"] is False


def test_e2e_application_serves_the_whole_wake_word_chain(tmp_path, monkeypatch):
    # 1. Page de diagnostic et modules du détecteur
    assert 'data-mode="vosk-wake"' in client.get("/static/audio_diag.html").text
    assert client.get("/static/js/wake_word_vosk.js").status_code == 200
    assert "registerProcessor" in client.get("/static/js/vosk_capture_worklet.js").text

    # 2. Modèle servi en flux (limite Cloud Run de 32 Mio sur les réponses HTTP/1 de taille connue)
    model = tmp_path / "model.tar.gz"
    model.write_bytes(b"\x1f\x8b" + b"m" * 2048)
    monkeypatch.setattr(wake_word_router, "MODEL_PATH", model)
    res_model = client.get("/vosk/model.tar.gz?v=e2e")
    assert res_model.status_code == 200
    assert "content-length" not in res_model.headers

    # 3. Service worker : modules pré-cachés pour le démarrage hors ligne, modèle jamais recopié
    sw = client.get("/sw.js").text
    assets = re.search(r"ASSETS_TO_CACHE = \[(.*?)\];", sw, re.S).group(1)
    assert '"/static/js/wake_word_vosk.js"' in assets
    assert 'url.pathname.startsWith("/vosk/")' in sw

    # 4. Branchement PWA : « Otis » → bip → dictée, échec explicite → mains-libres coupé
    speech = client.get("/static/js/speech.js").text
    assert "new VoskWakeWordDetector(" in speech
    assert "continuous = true" not in speech
    assert "triggerWakeCapture(" in speech
    assert "setWakeWordEnabled(false)" in speech

    # 5. La dictée déclenchée par le mot-clé aboutit sur un endpoint protégé par clé d'API
    #    (clé configurée : refus avant toute transcription, donc aucun appel Gemini)
    monkeypatch.setattr(settings, "api_key", "e2e-configured-key")
    res_audio = client.post(
        "/api/v1/interact/audio",
        files={"audio_file": ("otis.webm", b"\x1a\x45\xdf\xa3", "audio/webm")},
        headers={"X-API-Key": "invalid-e2e-key"},
    )
    assert res_audio.status_code == 401
