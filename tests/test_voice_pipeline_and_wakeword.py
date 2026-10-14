"""Tests unitaires et fonctionnels TDD pour le Pipeline Vocal PWA, la stabilité tactile du Push-to-Talk et le Wake-Word Otis (Étape 2)."""
import os
import re
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock, patch
from app.main import app
from app.core.audio.phonetic_normalizer import normalize_phonetics
from app.core.audio.stt_service import AudioSTTService

client = TestClient(app)


def test_phonetic_normalizer_covers_extended_otis_variants():
    """Vérifie la normalisation phonétique enrichie pour 'Otis' sous toutes ses formes usuelles."""
    assert normalize_phonetics("Dis autiste donne-moi mon programme") == "Dis Otis donne-moi mon programme"
    assert normalize_phonetics("Au tisse prépare la séance") == "Otis prépare la séance"
    assert normalize_phonetics("Notice note pour demain") == "Otis note pour demain"
    assert normalize_phonetics("Oh tisse tu m'entends") == "Otis tu m'entends"
    assert normalize_phonetics("Hotis ajoute du pain") == "Otis ajoute du pain"
    assert normalize_phonetics("Hostis annule la dernière action") == "Otis annule la dernière action"


def test_stt_service_cleans_multimodal_mime_types():
    """Vérifie que les paramètres de codecs (ex: audio/webm;codecs=opus) et formats vidéo sont assainis pour Gemini."""
    mock_client = MagicMock()
    mock_client.is_configured = True
    service = AudioSTTService(gemini_client=mock_client)

    # 1. audio/webm;codecs=opus -> audio/webm
    payload1 = service.build_multimodal_gemini_payload(b"TEST", mime_type="audio/webm;codecs=opus")
    assert payload1["contents"][0]["parts"][0]["inlineData"]["mimeType"] == "audio/webm"

    # 2. video/mp4 (Safari iOS audio-only recording container) -> audio/mp4
    payload2 = service.build_multimodal_gemini_payload(b"TEST", mime_type="video/mp4")
    assert payload2["contents"][0]["parts"][0]["inlineData"]["mimeType"] == "audio/mp4"

    # 3. audio/ogg; codecs=opus -> audio/ogg
    payload3 = service.build_multimodal_gemini_payload(b"TEST", mime_type="audio/ogg; codecs=opus")
    assert payload3["contents"][0]["parts"][0]["inlineData"]["mimeType"] == "audio/ogg"


def test_interact_audio_accepts_mp4_safari_container():
    """Vérifie que l'endpoint /api/v1/interact/audio accepte les conteneurs Safari (video/mp4 ou audio/mp4)."""
    with patch("app.routers.interact.get_stt_service") as mock_get_stt:
        mock_stt_inst = MagicMock()
        mock_parsed = MagicMock()
        mock_parsed.intent.value = "unknown"
        mock_parsed.parameters = {}
        mock_stt_inst.process_audio = AsyncMock(return_value=("Bonjour Otis", mock_parsed))
        mock_get_stt.return_value = mock_stt_inst

        # Fichier audio MP4 issu d'iOS Safari
        files = {"audio_file": ("recording.mp4", b"DUMMY_MP4_AUDIO", "video/mp4")}
        res = client.post("/api/v1/interact/audio", files=files)
        assert res.status_code == 200, f"Erreur status: {res.status_code} - {res.text}"
        data = res.json()
        assert data["transcribed_text"] == "Bonjour Otis"


def test_frontend_speech_js_implements_extended_wake_word_and_pointer_capture():
    """Vérifie que speech.js intègre les variantes phonétiques complètes, le calibrage et pointer capture."""
    res = client.get("/static/js/speech.js")
    assert res.status_code == 200
    content = res.text

    # 1. Variantes phonétiques par défaut
    assert "DEFAULT_WAKE_VARIANTS" in content
    assert "autiste" in content
    assert "au tisse" in content
    assert "isWakeWordMatch" in content

    # 2. Calibrage in-app
    assert "startWakeWordCalibration" in content or "addCustomWakeVariant" in content

    # 3. Stabilité tactile avec pointer capture
    assert "setPointerCapture" in content
    assert "releasePointerCapture" in content


def test_frontend_api_js_has_dynamic_mimetype_and_timeout_abort_controller():
    """Vérifie que postInteractAudio gère dynamiquement l'extension et protège contre les blocages réseau via AbortController."""
    res = client.get("/static/js/api.js")
    assert res.status_code == 200
    content = res.text

    assert "AbortController" in content
    assert "recording.mp4" in content or "mime.includes" in content


def test_frontend_chat_view_updates_user_bubble_with_transcription():
    """Vérifie que chat_view.js met à jour la bulle utilisateur avec transcribed_text."""
    res = client.get("/static/js/views/chat_view.js")
    assert res.status_code == 200
    content = res.text

    assert "transcribed_text" in content


def test_frontend_style_css_fixes_voice_dock_and_disables_elastic_scroll():
    """Vérifie que style.css fixe le dock vocal et neutralise le drag/scroll intempestif au toucher."""
    res = client.get("/static/style.css")
    assert res.status_code == 200
    content = res.text

    # Positionnement fixe
    assert "position: fixed" in content or "position:fixed" in content
    # Neutralisation du scroll et callout tactile
    assert "touch-action: none" in content or "touch-action:none" in content
    assert "user-select: none" in content or "user-select:none" in content


def test_frontend_index_html_has_wake_indicator_and_calibration_ui():
    """Vérifie que index.html contient le témoin visuel du mot-clé et les contrôles d'étalonnage."""
    res = client.get("/app")
    assert res.status_code == 200
    html = res.text

    assert 'id="wake-word-indicator"' in html
    assert 'id="btn-start-calibration"' in html or 'btn-calibrate-wakeword' in html


def test_frontend_speech_js_guarantees_wake_trigger_fallback_and_hands_free_vad():
    """Vérifie que speech.js intègre le fallback de déclenchement, l'extraction de commande continue, le chime et le VAD forcé."""
    res = client.get("/static/js/speech.js")
    assert res.status_code == 200
    content = res.text

    # 1. Extraction de commande enchaînée après mot-clé
    assert "extractCommandAfterWakeWord" in content

    # 2. Carillon sonore de confirmation auditive
    assert "playWakeChime" in content

    # 3. Déclencheur garanti (fallback même si startWakeWordDetection est appelé sans callback)
    assert "defaultWakeTrigger" in content or "triggerWakeCapture" in content

    # 4. Forçage du VAD mains-libres lors du réveil vocal
    assert "forceVad" in content or "isWakeTriggered" in content

