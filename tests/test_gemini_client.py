"""Tests unitaires pour le client Google Gemini et l'auto-découverte du modèle."""
import pytest
import httpx
from unittest.mock import AsyncMock, patch

from app.config import Settings
from app.core.llm.gemini_client import GeminiClient, DEFAULT_FALLBACK_MODEL


def test_gemini_settings_defaults():
    """Vérifie les variables de configuration par défaut pour Gemini."""
    settings = Settings()
    assert hasattr(settings, "gemini_api_key")
    assert hasattr(settings, "gemini_model")
    assert settings.gemini_model == "auto"


@pytest.mark.asyncio
async def test_resolve_model_explicit_config():
    """Si un modèle explicite est configuré (non 'auto'), il doit être retourné directement."""
    client = GeminiClient(api_key="fake-key", model="gemini-1.5-flash")
    resolved = await client.resolve_model()
    assert resolved == "gemini-1.5-flash"


@pytest.mark.asyncio
async def test_resolve_model_auto_discovery_selects_latest_stable_flash():
    """L'auto-découverte doit sélectionner le modèle Flash stable ayant la plus haute version."""
    mock_models_response = {
        "models": [
            {
                "name": "models/gemini-1.5-pro",
                "supportedGenerationMethods": ["generateContent"],
            },
            {
                "name": "models/gemini-1.5-flash",
                "supportedGenerationMethods": ["generateContent"],
            },
            {
                "name": "models/gemini-2.0-flash",
                "supportedGenerationMethods": ["generateContent"],
            },
            {
                "name": "models/gemini-2.0-flash-thinking-exp-01-21",
                "supportedGenerationMethods": ["generateContent"],
            },
            {
                "name": "models/text-embedding-004",
                "supportedGenerationMethods": ["embedContent"],
            },
        ]
    }

    client = GeminiClient(api_key="fake-key", model="auto")

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: mock_models_response
        mock_resp.raise_for_status = lambda: None
        mock_get.return_value = mock_resp

        resolved = await client.resolve_model()
        assert resolved == "gemini-2.0-flash"
        assert mock_get.call_count == 1


@pytest.mark.asyncio
async def test_resolve_model_caches_selection():
    """La résolution ne doit pas réinterroger l'API lors d'appels subséquents."""
    mock_models_response = {
        "models": [
            {
                "name": "models/gemini-2.0-flash",
                "supportedGenerationMethods": ["generateContent"],
            },
        ]
    }

    client = GeminiClient(api_key="fake-key", model="auto")

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: mock_models_response
        mock_resp.raise_for_status = lambda: None
        mock_get.return_value = mock_resp

        first_call = await client.resolve_model()
        second_call = await client.resolve_model()

        assert first_call == "gemini-2.0-flash"
        assert second_call == "gemini-2.0-flash"
        assert mock_get.call_count == 1  # Appelé une seule fois grâce au cache


@pytest.mark.asyncio
async def test_resolve_model_network_error_fallback():
    """En cas d'erreur réseau, le client doit retomber sur le modèle de repli sans lever d'exception."""
    client = GeminiClient(api_key="fake-key", model="auto")

    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Network unreachable")):
        resolved = await client.resolve_model()
        assert resolved == DEFAULT_FALLBACK_MODEL


@pytest.mark.asyncio
async def test_resolve_model_without_api_key_fallback():
    """Sans clé API configurée, le client renvoie immédiatement le modèle de repli."""
    client = GeminiClient(api_key="", model="auto")
    resolved = await client.resolve_model()
    assert resolved == DEFAULT_FALLBACK_MODEL


@pytest.mark.asyncio
async def test_live_gemini_auto_discovery():
    """Test réel d'interrogation de l'API Google Gemini si une clé valide est présente."""
    from app.config import settings as app_settings
    if not app_settings.gemini_api_key or app_settings.gemini_api_key.startswith("fake"):
        pytest.skip("Aucune clé GEMINI_API_KEY réelle configurée.")

    client = GeminiClient(api_key=app_settings.gemini_api_key, model="auto")
    resolved = await client.resolve_model(force_refresh=True)
    assert resolved.startswith("gemini-")
    assert "flash" in resolved.lower()


def test_quota_guard_and_usage_stats():
    """Vérifie le fonctionnement du compteur de requêtes, du garde-fou et des statistiques."""
    client = GeminiClient(api_key="fake-key", max_daily_requests=2)
    assert client.is_daily_quota_exceeded() is False

    stats = client.get_usage_stats()
    assert stats["daily_requests"] == 0
    assert stats["max_daily_requests"] == 2
    assert stats["remaining_daily_requests"] == 2
    assert stats["quota_exceeded"] is False

    # 1ère requête enregistrée
    client.record_request(latency_ms=185.4)
    stats = client.get_usage_stats()
    assert stats["daily_requests"] == 1
    assert stats["remaining_daily_requests"] == 1
    assert stats["last_latency_ms"] == 185.4
    assert stats["quota_exceeded"] is False

    # 2ème requête enregistrée -> Quota atteint
    client.record_request(latency_ms=210.0)
    assert client.is_daily_quota_exceeded() is True
    stats = client.get_usage_stats()
    assert stats["daily_requests"] == 2
    assert stats["remaining_daily_requests"] == 0
    assert stats["quota_exceeded"] is True


def test_llm_stats_endpoint():
    """Vérifie que l'endpoint /api/v1/llm/stats expose les statistiques du client Gemini."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/v1/llm/stats")
    assert response.status_code == 200
    data = response.json()
    assert "daily_requests" in data
    assert "max_daily_requests" in data
    assert "remaining_daily_requests" in data
    assert "model" in data
    assert "quota_exceeded" in data
