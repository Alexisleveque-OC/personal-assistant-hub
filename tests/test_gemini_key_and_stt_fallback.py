"""Clé Gemini jamais dans une URL (fuite constatée le 04/11 : l'URL avec ?key= est remontée jusqu'au téléphone)
et repli de la transcription audio sur des modèles capables de transcrire, avec un message d'échec clair."""
import io
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.audio.stt_service import AudioSTTService, STTUnavailableError, set_stt_service
from app.core.llm.gemini_client import GeminiClient
from app.main import app

APP_DIR = Path(__file__).resolve().parent.parent / "app"
SECRET = "SECRET-KEY-123"


def test_no_gemini_call_puts_the_api_key_in_the_url():
    offenders = []
    for path in APP_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"\?key=|params=\{\s*\"key\"", text):
            offenders.append(str(path.relative_to(APP_DIR)))
    assert offenders == []


def test_image_generation_models_are_not_fallback_candidates():
    client = GeminiClient(api_key="fake-key", model="auto")
    models = [
        {"name": f"models/{name}", "supportedGenerationMethods": ["generateContent"]}
        for name in ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite-image", "gemini-3.1-flash-image-preview", "gemini-3.6-flash")
    ]
    client._select_best_flash_model(models)
    assert client.get_candidate_models() == ["gemini-3.5-flash-lite", "gemini-3.6-flash"]


def _client(candidates):
    client = MagicMock()
    client.is_configured = True
    client.api_key = SECRET
    client.timeout = 5.0
    client.is_daily_quota_exceeded.return_value = False
    client.resolve_model = AsyncMock(return_value=candidates[0])
    client.get_candidate_models.return_value = list(candidates)
    return client


def _response(status: int, text: str = '{"transcribed_text": "ajoute du lait", "intent": "unknown", "parameters": {}}'):
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/m:generateContent")
    if status != 200:
        return httpx.Response(status, json={"error": {"message": "boom"}}, request=request)
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]}, request=request)


@pytest.mark.asyncio
async def test_stt_sends_the_key_in_a_header_and_falls_back_to_the_next_model():
    service = AudioSTTService(gemini_client=_client(["lite", "flash"]))
    calls = []

    async def fake_post(self, url, **kwargs):
        calls.append((url, kwargs.get("headers", {})))
        return _response(429) if "lite" in url else _response(200)

    with patch("httpx.AsyncClient.post", fake_post):
        text, _ = await service.process_audio(b"AUDIO", mime_type="audio/webm")

    assert text == "ajoute du lait"
    assert [url.rsplit("/", 1)[-1] for url, _ in calls] == ["lite:generateContent", "flash:generateContent"]
    assert all(SECRET not in url and headers.get("x-goog-api-key") == SECRET for url, headers in calls)


@pytest.mark.asyncio
async def test_stt_failure_lists_every_model_without_leaking_the_key():
    service = AudioSTTService(gemini_client=_client(["lite", "flash", "pro"]))
    statuses = {"lite": 429, "flash": 503, "pro": 400}

    async def fake_post(self, url, **kwargs):
        model = url.rsplit("/", 1)[-1].split(":")[0]
        return _response(statuses[model])

    with patch("httpx.AsyncClient.post", fake_post):
        with pytest.raises(STTUnavailableError) as err:
            await service.process_audio(b"AUDIO", mime_type="audio/webm")

    message = str(err.value)
    assert "lite : quota atteint (429)" in message
    assert "flash : surchargé (503)" in message
    assert "pro : requête refusée (400)" in message
    assert SECRET not in message and "googleapis" not in message
    assert err.value.user_message == "Je n'ai pas pu transcrire ton message : quota Gemini atteint ou service surchargé. Réessaie dans un instant ou tape-le."


def test_audio_endpoint_returns_the_clear_message_only():
    failing = MagicMock()
    failing.process_audio = AsyncMock(side_effect=STTUnavailableError(
        "lite : quota atteint (429)",
        user_message="Je n'ai pas pu transcrire ton message : quota Gemini atteint ou service surchargé. Réessaie dans un instant ou tape-le.",
    ))
    set_stt_service(failing)
    try:
        resp = TestClient(app).post(
            "/api/v1/interact/audio",
            files={"audio_file": ("r.webm", io.BytesIO(b"AUDIO"), "audio/webm")},
        )
    finally:
        set_stt_service(None)
    assert resp.status_code == 503
    assert resp.json()["detail"].startswith("Je n'ai pas pu transcrire ton message")
    assert "429" not in resp.json()["detail"]
