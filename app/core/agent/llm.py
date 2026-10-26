"""Accès au LLM de l'agent : interface `AgentLLM` et implémentation REST Gemini `generateContent`.

Format (doc officielle Gemini) : `tools: [{functionDeclarations: [...]}]`, parts `functionCall` en réponse,
parts `functionResponse` (rôle `user`) en retour. Les parts du modèle sont conservées brutes pour être
renvoyées à l'identique : sur Gemini 3, omettre le `thoughtSignature` d'un appel de fonction donne une erreur 400.
"""
import logging
import time
from typing import Any, Dict, List, Optional, Protocol

import httpx
from pydantic import BaseModel, Field

from app.core.agent.errors import AgentLLMError, AgentResponseError, AgentUnavailableError
from app.core.llm.gemini_client import GEMINI_API_BASE_URL, GeminiClient

logger = logging.getLogger(__name__)

__all__ = [
    "AgentLLM", "AgentLLMError", "AgentResponseError", "AgentUnavailableError",
    "FunctionCall", "GeminiAgentLLM", "LLMTurn",
]

_RETRYABLE_STATUSES = {404, 500, 503}


class FunctionCall(BaseModel):
    name: str
    args: Dict[str, Any] = Field(default_factory=dict)
    id: Optional[str] = None


class LLMTurn(BaseModel):
    """Tour du modèle. `parts` reste brut : il est renvoyé tel quel dans l'historique (signatures)."""
    parts: List[Dict[str, Any]]
    finish_reason: Optional[str] = None

    def function_calls(self) -> List[FunctionCall]:
        return [FunctionCall.model_validate(p["functionCall"]) for p in self.parts if "functionCall" in p]

    def text(self) -> str:
        return "".join(p["text"] for p in self.parts if "text" in p and not p.get("thought")).strip()


class AgentLLM(Protocol):
    async def generate(
        self, *, system_instruction: str, contents: List[Dict[str, Any]], tools: List[Dict[str, Any]]
    ) -> LLMTurn: ...


class GeminiAgentLLM:
    def __init__(self, client: GeminiClient, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self.client = client
        self._transport = transport

    async def generate(
        self, *, system_instruction: str, contents: List[Dict[str, Any]], tools: List[Dict[str, Any]]
    ) -> LLMTurn:
        if not self.client.is_configured:
            raise AgentUnavailableError("Clé GEMINI_API_KEY absente : l'agent ne peut pas raisonner.")
        if self.client.is_daily_quota_exceeded():
            raise AgentUnavailableError(
                f"Garde-fou de quota journalier Gemini atteint ({self.client.max_daily_requests} requêtes)."
            )

        payload = {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": contents,
            "tools": [{"functionDeclarations": tools}],
        }
        failures: List[str] = []
        async with httpx.AsyncClient(timeout=self.client.timeout, transport=self._transport) as http:
            for model in await self._candidate_models():
                start = time.perf_counter()
                try:
                    response = await http.post(
                        f"{GEMINI_API_BASE_URL}/models/{model}:generateContent",
                        headers={"x-goog-api-key": self.client.api_key},
                        json=payload,
                    )
                except httpx.HTTPError as exc:
                    failures.append(f"{model} : {type(exc).__name__}")
                    continue
                if response.status_code == 429:
                    self.client.mark_model_temporarily_unavailable(model, 60.0)
                    failures.append(f"{model} : HTTP 429 (débit/quota)")
                    continue
                if response.status_code in _RETRYABLE_STATUSES:
                    failures.append(f"{model} : HTTP {response.status_code}")
                    continue
                if response.status_code >= 400:
                    raise AgentLLMError(
                        f"Requête refusée par Gemini {model} (HTTP {response.status_code}) : {_api_message(response)}"
                    )
                self.client.record_request((time.perf_counter() - start) * 1000)
                self.client.set_active_working_model(model)
                return _parse_turn(response.json())

        logger.warning(f"Agent : aucun modèle Gemini disponible ({failures}).")
        raise AgentUnavailableError(f"Aucun modèle Gemini disponible : {'; '.join(failures)}.")

    async def _candidate_models(self) -> List[str]:
        models = [await self.client.resolve_model()]
        models += [m for m in self.client.get_candidate_models() if m not in models]
        return models


def _api_message(response: httpx.Response) -> str:
    try:
        return response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return response.text[:300]


def _parse_turn(data: Dict[str, Any]) -> LLMTurn:
    candidates = data.get("candidates") or []
    if not candidates:
        reason = (data.get("promptFeedback") or {}).get("blockReason", "inconnue")
        raise AgentResponseError(f"Gemini n'a renvoyé aucune réponse (raison du blocage : {reason}).")
    candidate = candidates[0]
    return LLMTurn(
        parts=(candidate.get("content") or {}).get("parts") or [],
        finish_reason=candidate.get("finishReason"),
    )
