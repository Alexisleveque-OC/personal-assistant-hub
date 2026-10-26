"""Tests du client LLM Gemini de l'agent (REST generateContent avec function calling), HTTP simulé."""
import json

import httpx
import pytest

from app.core.agent.llm import AgentLLMError, AgentResponseError, AgentUnavailableError, GeminiAgentLLM
from app.core.llm.gemini_client import GeminiClient

TOOLS = [{"name": "find_sport_sessions", "description": "d", "parameters": {"type": "object", "properties": {}}}]
CONTENTS = [{"role": "user", "parts": [{"text": "Salut"}]}]


def _client(models=("m1",), max_daily_requests=100) -> GeminiClient:
    client = GeminiClient(api_key="test-key", model=models[0], max_daily_requests=max_daily_requests)
    client._candidate_models = list(models)
    return client


def _ok(parts, finish="STOP"):
    return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": finish}]})


async def _generate(llm: GeminiAgentLLM):
    return await llm.generate(system_instruction="Tu es Otis.", contents=CONTENTS, tools=TOOLS)


@pytest.mark.asyncio
async def test_request_payload_and_parsed_turn():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _ok([{"functionCall": {"name": "find_sport_sessions", "args": {}}, "thoughtSignature": "abc"}])

    client = _client()
    turn = await _generate(GeminiAgentLLM(client, transport=httpx.MockTransport(handler)))

    request = seen[0]
    assert request.url.path.endswith("/models/m1:generateContent")
    payload = json.loads(request.content)
    assert payload["systemInstruction"] == {"parts": [{"text": "Tu es Otis."}]}
    assert payload["contents"] == CONTENTS
    assert payload["tools"] == [{"functionDeclarations": TOOLS}]
    assert turn.parts[0]["thoughtSignature"] == "abc"
    assert turn.function_calls()[0].name == "find_sport_sessions"
    assert client.get_usage_stats()["daily_requests"] == 1


@pytest.mark.asyncio
async def test_rate_limited_model_falls_back_to_next_candidate():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if "/m1:" in request.url.path:
            return httpx.Response(429, json={"error": {"message": "quota"}})
        return _ok([{"text": "ok"}])

    turn = await _generate(GeminiAgentLLM(_client(("m1", "m2")), transport=httpx.MockTransport(handler)))
    assert turn.text() == "ok"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_all_candidates_unavailable_raises_explicit_error():
    transport = httpx.MockTransport(lambda r: httpx.Response(503, text="overloaded"))
    with pytest.raises(AgentUnavailableError, match="m1"):
        await _generate(GeminiAgentLLM(_client(), transport=transport))


@pytest.mark.asyncio
async def test_bad_request_fails_fast_with_api_message():
    transport = httpx.MockTransport(lambda r: httpx.Response(400, json={"error": {"message": "Missing thought signature"}}))
    with pytest.raises(AgentLLMError, match="thought signature"):
        await _generate(GeminiAgentLLM(_client(("m1", "m2")), transport=transport))


@pytest.mark.asyncio
async def test_missing_api_key_or_quota_exceeded_raise_before_any_call():
    transport = httpx.MockTransport(lambda r: pytest.fail("aucun appel HTTP attendu"))
    with pytest.raises(AgentUnavailableError, match="GEMINI_API_KEY"):
        await _generate(GeminiAgentLLM(GeminiClient(api_key="", model="m1"), transport=transport))
    with pytest.raises(AgentUnavailableError, match="quota"):
        await _generate(GeminiAgentLLM(_client(max_daily_requests=0), transport=transport))


@pytest.mark.asyncio
async def test_blocked_prompt_without_candidates_raises():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}))
    with pytest.raises(AgentResponseError, match="SAFETY"):
        await _generate(GeminiAgentLLM(_client(), transport=transport))
