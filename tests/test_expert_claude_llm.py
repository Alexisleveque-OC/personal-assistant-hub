"""Connecteur Claude de l'expert : requête envoyée au SDK officiel, lecture de la réponse, erreurs explicites (hors ligne)."""
from types import SimpleNamespace
from typing import Any, Dict, List

import anthropic
import httpx2
import pytest

from app.core.agent.tool_registry import AgentTool, ToolRegistry
from app.core.expert.errors import ExpertLLMError, ExpertUnavailableError
from app.core.expert.llm import EXPERT_FALLBACK_BETA, ClaudeExpertLLM


class _Block:
    def __init__(self, **data: Any) -> None:
        self._data = data
        self.type = data["type"]

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data)


class FakeMessages:
    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome
        self.calls: List[Dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _client(outcome: Any) -> SimpleNamespace:
    return SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages(outcome)))


def _message(*blocks: _Block, stop_reason: str = "end_turn") -> SimpleNamespace:
    usage = SimpleNamespace(input_tokens=120, output_tokens=40, cache_read_input_tokens=10, cache_creation_input_tokens=None)
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason, model="claude-sonnet-5-5", usage=usage)


def _request() -> httpx2.Request:
    return httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def _status_error(cls: type, status: int, message: str) -> Exception:
    response = httpx2.Response(status, request=_request(), json={"error": {"message": message}})
    return cls(message, response=response, body={"error": {"message": message}})


async def _generate(llm: ClaudeExpertLLM):
    return await llm.generate(system="Consigne", messages=[{"role": "user", "content": "Q"}], tools=[], max_tokens=600)


@pytest.mark.asyncio
async def test_request_uses_sonnet_low_effort_fallbacks_and_reads_the_answer():
    client = _client(_message(_Block(type="thinking", thinking="", signature="s"), _Block(type="text", text="Réponse.")))
    llm = ClaudeExpertLLM(api_key="k", model="claude-sonnet-5-5", client=client)

    turn = await _generate(llm)

    call = client.beta.messages.calls[0]
    assert call["model"] == "claude-sonnet-5-5"
    assert call["max_tokens"] == 600
    assert call["system"] == "Consigne"
    assert call["output_config"] == {"effort": "low"}
    assert call["betas"] == [EXPERT_FALLBACK_BETA] and call["fallbacks"] == "default"
    assert "tools" not in call  # aucun outil : le paramètre n'est pas envoyé
    assert turn.text() == "Réponse."
    assert turn.content[0]["type"] == "thinking"  # renvoyé tel quel au tour suivant
    assert (turn.usage.input_tokens, turn.usage.output_tokens, turn.usage.cache_read_input_tokens) == (120, 40, 10)
    assert turn.usage.cache_creation_input_tokens == 0
    assert llm.last_model == "claude-sonnet-5-5"


@pytest.mark.asyncio
async def test_missing_key_is_reported_without_calling_the_api():
    client = _client(_message())
    with pytest.raises(ExpertUnavailableError, match="ANTHROPIC_API_KEY"):
        await _generate(ClaudeExpertLLM(api_key="", client=client))
    assert client.beta.messages.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [
    anthropic.APIConnectionError(request=_request()),
    anthropic.APITimeoutError(request=_request()),
    _status_error(anthropic.RateLimitError, 429, "rate limited"),
    _status_error(anthropic.InternalServerError, 500, "boom"),
    _status_error(anthropic.AuthenticationError, 401, "invalid x-api-key"),
])
async def test_transient_and_auth_failures_make_the_expert_unavailable(error):
    with pytest.raises(ExpertUnavailableError):
        await _generate(ClaudeExpertLLM(api_key="k", client=_client(error)))


@pytest.mark.asyncio
async def test_rejected_request_is_a_format_error_with_the_api_message():
    error = _status_error(anthropic.BadRequestError, 400, "tools.0.input_schema: invalid")
    with pytest.raises(ExpertLLMError, match="input_schema"):
        await _generate(ClaudeExpertLLM(api_key="k", client=_client(error)))


def test_registry_exposes_tools_in_claude_format():
    from pydantic import BaseModel, Field

    class Args(BaseModel):
        article: str = Field(description="Nom de l'article")

    registry = ToolRegistry([AgentTool("add_item", "Ajoute un article", Args, lambda a: a)])
    [tool] = registry.claude_declarations()
    assert tool["name"] == "add_item"
    assert tool["description"] == "Ajoute un article"
    assert tool["input_schema"]["type"] == "object"
    assert tool["input_schema"]["properties"]["article"]["description"] == "Nom de l'article"
    assert tool["input_schema"]["required"] == ["article"]
