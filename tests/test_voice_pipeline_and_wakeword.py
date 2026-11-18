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


def test_frontend_index_html_has_wake_indicator():
    """Vérifie que index.html contient le témoin visuel du mot-clé."""
    res = client.get("/app")
    assert res.status_code == 200
    html = res.text

    assert 'id="wake-word-indicator"' in html
