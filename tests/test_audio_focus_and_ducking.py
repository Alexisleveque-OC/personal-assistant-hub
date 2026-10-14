"""Tests unitaires et fonctionnels TDD pour la gestion de l'Audio Focus & Ducking casque en mode running (Étape 1)."""
import os
import re
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_audio_focus_module_is_served_and_valid():
    """Vérifie que le module static /static/js/audio_focus.js est servi correctement."""
    res = client.get("/static/js/audio_focus.js")
    assert res.status_code == 200
    assert "javascript" in res.headers.get("content-type", "")
    content = res.text

    # Vérification des exports et méthodes clés du gestionnaire d'Audio Focus
    assert "export class AudioFocusManager" in content or "export const audioFocusManager" in content
    assert "requestDucking" in content
    assert "releaseDucking" in content
    assert "isDucking" in content
    assert "audioSession" in content
    assert '"ambient"' in content
    assert '"transient"' in content


def test_audio_focus_lifecycle_wiring_in_speech_js():
    """Vérifie que speech.js intègre audioFocusManager pour câbler le cycle vocal complet."""
    res = client.get("/static/js/speech.js")
    assert res.status_code == 200
    content = res.text

    # 1. Import du module audio_focus
    assert "audio_focus.js" in content
    assert "audioFocusManager" in content

    # 2. Câblage TTS : speak déclenche le ducking au début et restaure le volume nominal à la fin/erreur
    assert "requestDucking" in content
    assert "releaseDucking" in content
    assert "onstart" in content
    assert "onend" in content
    assert "onerror" in content

    # 3. Protection Anti-GC Chrome sur SpeechSynthesisUtterance et Watchdog
    assert "currentUtterance" in content or "activeUtterance" in content

    # 4. Enregistrement vocal (Push-to-Talk / VAD) : ducking à l'enregistrement et libération immédiate
    # stopAudioCapture doit libérer les pistes audio du microphone et fermer l'AudioContext
    assert "cleanupAudioNodes" in content

    # 5. Gestion non-intrusive du Wake-Word
    assert "startWakeWord" in content or "pauseWakeWord" in content or "stopWakeWord" in content


def test_service_worker_caches_audio_focus_module():
    """Vérifie que le Service Worker PWA met en cache le nouveau module audio_focus.js."""
    res = client.get("/sw.js")
    assert res.status_code == 200
    assert "audio_focus.js" in res.text


def test_app_js_initializes_audio_focus():
    """Vérifie que app.js initialise l'Audio Focus au démarrage sans réserver le micro."""
    res = client.get("/static/app.js")
    assert res.status_code == 200
    assert "audioFocusManager" in res.text or "audio_focus.js" in res.text
