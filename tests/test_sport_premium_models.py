"""Sport en production : meilleurs modèles Gemini d'abord (3.8 → 3.6 → 3.5 Lite), relais au modèle inférieur sur quota.

Les autres usages (agent, NLU, rayons) restent sur le modèle à gros quota (3.5 Flash Lite, 500 req/j) : un succès du
sport ne doit jamais promouvoir 3.8 (20 req/j) en tête des candidats de toute l'application.
"""
import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.llm.gemini_client import GeminiClient

DISCOVERED = [
    "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.1-flash-lite",
]


def _discovered_client() -> GeminiClient:
    client = GeminiClient(api_key="fake-key")
    client._resolved_model = client._select_best_flash_model(
        [{"name": f"models/{m}", "supportedGenerationMethods": ["generateContent"]} for m in DISCOVERED]
    )
    return client


def _response(status_code: int, text: str = "{}") -> MagicMock:
    response = MagicMock(status_code=status_code, text=text)
    response.json.return_value = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    response.raise_for_status.return_value = None
    return response


def _tried_models(mock_post: AsyncMock) -> list[str]:
    return [call.args[0].split("/models/")[1].split(":")[0] for call in mock_post.await_args_list]


@pytest.mark.asyncio
async def test_premium_candidates_are_ordered_best_first():
    client = _discovered_client()

    assert await client.premium_candidate_models() == [
        "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite",
    ]
    assert client.get_candidate_models()[0] == "gemini-3.5-flash-lite"  # le reste de l'appli n'est pas concerné


@pytest.mark.asyncio
async def test_premium_candidates_skip_models_whose_quota_is_exhausted():
    client = _discovered_client()
    client.mark_model_temporarily_unavailable("gemini-3.8-flash")

    assert (await client.premium_candidate_models())[0] == "gemini-3.7-flash"


@pytest.mark.asyncio
async def test_premium_candidates_resolve_the_models_when_not_yet_discovered():
    client = GeminiClient(api_key="fake-key")
    with patch.object(client, "resolve_model", new_callable=AsyncMock) as resolve:
        await client.premium_candidate_models()

    resolve.assert_awaited_once()


@pytest.mark.asyncio
async def test_sport_vision_tries_the_best_model_first_without_promoting_it():
    from app.core.vision.sport_vision_service import SportVisionService

    client = _discovered_client()
    ok = _response(200, json.dumps({"date": None, "distance_km": 5.0, "duree_secondes": 1800}))
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=ok) as mock_post:
        await SportVisionService(gemini_client=client).analyze_screenshot(
            image_bytes=b"img", reference_date=date(2026, 10, 27)
        )

    assert _tried_models(mock_post) == ["gemini-3.8-flash"]
    assert client.get_candidate_models()[0] == "gemini-3.5-flash-lite"


@pytest.mark.asyncio
async def test_sport_coach_plan_falls_back_to_lower_models_on_quota():
    from app.connectors.sheets.sport_connector import SportConnector
    from app.core.sport_coach_service import SportCoachService

    client = _discovered_client()
    service = SportCoachService(connector=MagicMock(spec=SportConnector), gemini_client=client)
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=_response(429)) as mock_post:
        with pytest.raises(RuntimeError):
            await service._call_gemini_coach("système", "utilisateur")

    assert _tried_models(mock_post)[:4] == [
        "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite",
    ]


@pytest.mark.asyncio
async def test_sport_coach_tip_uses_the_best_model_without_promoting_it():
    from app.routers import sport as sport_router

    client = _discovered_client()
    ok = _response(200, json.dumps({"message": "Bonne sortie !", "niveau": "info"}))
    with patch("app.core.llm.gemini_client.get_gemini_client", return_value=client), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=ok) as mock_post:
        tip = await sport_router._call_gemini_coach_tip({"forme": "bonne"})

    assert tip.message == "Bonne sortie !"
    assert _tried_models(mock_post) == ["gemini-3.8-flash"]
    assert client.get_candidate_models()[0] == "gemini-3.5-flash-lite"
