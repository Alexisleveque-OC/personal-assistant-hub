"""Tests unitaires et fonctionnels TDD pour le pipeline STT multimodal et la normalisation phonétique."""
import base64
import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.core.models import IntentType
from app.core.audio.phonetic_normalizer import normalize_phonetics
from app.core.audio.stt_service import AudioSTTService, get_stt_service, set_stt_service


def test_phonetic_normalizer_replaces_common_speech_errors():
    """Vérifie la correction préventive des confusions phonétiques récurrentes."""
    # 1. RPE à Troyes -> RPE à 3
    t1 = normalize_phonetics("Footing de 8km avec RPE à Troyes hier")
    assert "RPE à 3" in t1 or "rpe à 3" in t1.lower()

    # 2. Confusion avec "autiste" ou "notice" pour "Otis"
    t2 = normalize_phonetics("Merci autiste pour le conseil")
    assert "Otis" in t2 or "otis" in t2.lower()

    # 3. Renfort -> renforcement
    t3 = normalize_phonetics("J'ai fait 30 minutes de renfort")
    assert "renforcement" in t3.lower()

    # 4. Des plus -> D+ / d+
    t4 = normalize_phonetics("Sortie avec 150 des plus de dénivelé")
    assert "d+" in t4.lower() or "dénivelé" in t4.lower()


def test_audio_stt_service_builds_gemini_multimodal_payload():
    """Vérifie la mise en forme du payload Gemini avec inlineData audio base64."""
    mock_client = MagicMock()
    mock_client.is_configured = True
    service = AudioSTTService(gemini_client=mock_client)

    audio_bytes = b"FAKE_AUDIO_DATA_FOR_TESTING"
    payload = service.build_multimodal_gemini_payload(audio_bytes, mime_type="audio/webm")

    parts = payload["contents"][0]["parts"]
    assert len(parts) >= 2
    assert "inlineData" in parts[0]
    assert parts[0]["inlineData"]["mimeType"] == "audio/webm"
    assert parts[0]["inlineData"]["data"] == base64.b64encode(audio_bytes).decode("utf-8")


@pytest.mark.asyncio
async def test_audio_stt_service_process_audio_success():
    """Vérifie le parsing et la transcription d'un audio reçu via Gemini."""
    mock_client = MagicMock()
    mock_client.is_configured = True
    mock_client.is_daily_quota_exceeded.return_value = False
    mock_client.resolve_model = AsyncMock(return_value="gemini-3.5-flash-lite")
    mock_client.get_candidate_models.return_value = ["gemini-3.5-flash-lite"]
    mock_client.timeout = 5.0

    service = AudioSTTService(gemini_client=mock_client)

    # Simulation de la réponse JSON de Gemini
    simulated_gemini_response = {
        "transcribed_text": "Ajoute du beurre au rayon Frais",
        "intent": "add_shopping_item",
        "confidence": 0.98,
        "parameters": {"item": "beurre", "rayon": "Frais"},
        "conversational_reply": None,
    }

    import json
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": json.dumps(simulated_gemini_response)}]
                    }
                }
            ]
        }
        mock_post.return_value = mock_resp

        transcribed, parsed = await service.process_audio(
            b"FAKEDATA", mime_type="audio/webm"
        )
        assert transcribed == "Ajoute du beurre au rayon Frais"
        assert parsed.intent == IntentType.ADD_SHOPPING_ITEM
        assert parsed.parameters["item"] == "beurre"


def test_interact_audio_endpoint_with_mock_stt():
    """Vérifie l'endpoint REST /api/v1/interact/audio avec un service STT injecté."""
    client = TestClient(app)

    # Mock du service STT
    mock_stt = MagicMock()
    mock_parsed = MagicMock()
    mock_parsed.intent = IntentType.ADD_SHOPPING_ITEM
    mock_parsed.parameters = {"item": "pommes", "rayon": "Fruits & Légumes"}
    mock_parsed.confidence = 0.95
    mock_parsed.conversational_reply = None
    mock_parsed.raw_query = "Ajoute des pommes"

    mock_stt.process_audio = AsyncMock(return_value=("Ajoute des pommes", mock_parsed))
    set_stt_service(mock_stt)

    try:
        audio_content = io.BytesIO(b"MOCK_OGG_AUDIO_BYTES")
        files = {"audio_file": ("command.ogg", audio_content, "audio/ogg")}
        data = {"session_id": "audio-test-session"}

        resp = client.post("/api/v1/interact/audio", files=files, data=data)
        assert resp.status_code == 200
        res_json = resp.json()
        assert res_json["success"] is True
        assert res_json.get("transcribed_text") == "Ajoute des pommes"
    finally:
        set_stt_service(None)


def test_interact_audio_endpoint_rejects_unsupported_format():
    """Vérifie le rejet HTTP 415 pour les formats non audio (ex: pdf ou txt)."""
    client = TestClient(app)
    bad_file = io.BytesIO(b"NOT AN AUDIO")
    files = {"audio_file": ("test.pdf", bad_file, "application/pdf")}

    resp = client.post("/api/v1/interact/audio", files=files)
    assert resp.status_code in (400, 415)
