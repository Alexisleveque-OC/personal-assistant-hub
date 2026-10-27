"""Suggestion par Gemini de 2 rayons plausibles pour un article inconnu (Phase 6.8)."""
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.llm.gemini_client import GeminiClient
from app.core.llm.rayon_suggester import GeminiRayonSuggester

RAYONS = ["Fruits & Légumes", "Frais", "Épicerie", "Hygiène", "Entretien", "Divers"]


def _response(status: int, payload: dict) -> httpx.Response:
    return httpx.Response(status, json=payload, request=httpx.Request("POST", "https://gemini.test"))


def _answer(rayons: list) -> httpx.Response:
    text = json.dumps({"rayons": rayons}, ensure_ascii=False)
    return _response(200, {"candidates": [{"content": {"parts": [{"text": text}]}}]})


def _suggester() -> GeminiRayonSuggester:
    return GeminiRayonSuggester(GeminiClient(api_key="fake-key", model="gemini-test"))


@pytest.mark.asyncio
async def test_two_rayons_of_the_sheet_are_suggested_and_divers_is_never_offered():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=_answer(["Entretien", "Épicerie"])) as post:
        suggestions = await _suggester()("Papier cadeau", RAYONS)

    assert suggestions == ["Entretien", "Épicerie"]
    schema = post.call_args.kwargs["json"]["generationConfig"]["responseSchema"]
    assert schema["properties"]["rayons"]["items"]["enum"] == ["Fruits & Légumes", "Frais", "Épicerie", "Hygiène", "Entretien"]


@pytest.mark.asyncio
async def test_suggestions_are_matched_case_insensitively_on_the_sheet_spelling():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=_answer(["entretien", "HYGIÈNE"])):
        assert await _suggester()("Bougies", RAYONS) == ["Entretien", "Hygiène"]


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", [["Entretien"], ["Entretien", "Entretien"], ["Entretien", "Bricolage"], ["Divers", "Frais"]])
async def test_an_unusable_answer_gives_no_suggestion(answer):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=_answer(answer)):
        assert await _suggester()("Bougies", RAYONS) == []


@pytest.mark.asyncio
async def test_unavailable_gemini_gives_no_suggestion():
    quota = _response(429, {"error": {"message": "quota"}})
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=quota):
        assert await _suggester()("Bougies", RAYONS) == []


@pytest.mark.asyncio
async def test_no_api_key_or_fewer_than_two_rayons_skips_the_call():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as post:
        assert await GeminiRayonSuggester(GeminiClient(api_key=""))("Bougies", RAYONS) == []
        assert await _suggester()("Bougies", ["Frais", "Divers"]) == []

    post.assert_not_called()
