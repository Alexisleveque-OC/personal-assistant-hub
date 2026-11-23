"""Accès à Claude pour l'expert : interface `ExpertLLM` et implémentation par le SDK officiel `anthropic`.

Le contenu renvoyé par Claude est conservé brut (blocs `thinking` compris) pour être renvoyé à l'identique au tour
suivant, comme l'exige l'API. Repli serveur `fallbacks: "default"` : si Sonnet refuse, l'API relance la requête sur
le modèle de repli recommandé par Anthropic (facturé à son tarif).
"""
import logging
from typing import Any, Dict, List, Optional, Protocol

import anthropic
from pydantic import BaseModel

from app.config import settings
from app.core.expert.errors import ExpertLLMError, ExpertUnavailableError

logger = logging.getLogger(__name__)

EXPERT_DEFAULT_MODEL = "claude-sonnet-5-5"
EXPERT_FALLBACK_BETA = "server-side-fallback-2026-07-01"
EXPERT_EFFORT = "low"  # réponses orales : la latence prime sur la profondeur de réflexion


class ExpertUsage(BaseModel):
    """Tokens facturés pour un appel (base du calcul de coût)."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    model: Optional[str] = None


class ExpertTurn(BaseModel):
    content: List[Dict[str, Any]]
    stop_reason: Optional[str] = None
    model: Optional[str] = None
    usage: ExpertUsage = ExpertUsage()

    def tool_uses(self) -> List[Dict[str, Any]]:
        return [block for block in self.content if block.get("type") == "tool_use"]

    def text(self) -> str:
        return "".join(block["text"] for block in self.content if block.get("type") == "text").strip()


class ExpertLLM(Protocol):
    async def generate(
        self, *, system: str, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], max_tokens: int,
    ) -> ExpertTurn: ...


class ClaudeExpertLLM:
    def __init__(
        self, api_key: Optional[str] = None, model: Optional[str] = None, client: Any = None, timeout: float = 45.0,
    ) -> None:
        """`client` : client du SDK injecté (tests) ; sinon un `AsyncAnthropic` est créé au premier appel."""
        self.api_key = settings.anthropic_api_key if api_key is None else api_key
        self.model = model or settings.claude_expert_model or EXPERT_DEFAULT_MODEL
        self.timeout = timeout
        self._client = client
        self.last_model: Optional[str] = None

    def _sdk(self) -> Any:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=self.api_key, timeout=self.timeout, max_retries=1)
        return self._client

    async def generate(
        self, *, system: str, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], max_tokens: int,
    ) -> ExpertTurn:
        if not self.api_key:
            raise ExpertUnavailableError("Clé ANTHROPIC_API_KEY absente : l'expert Claude ne peut pas répondre.")
        request: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
            "output_config": {"effort": EXPERT_EFFORT},
            "betas": [EXPERT_FALLBACK_BETA],
            "fallbacks": "default",
        }
        if tools:
            request["tools"] = tools
        try:
            message = await self._sdk().beta.messages.create(**request)
        except anthropic.APIConnectionError as exc:  # délai dépassé compris
            raise ExpertUnavailableError(f"Claude injoignable ({type(exc).__name__}).") from exc
        except anthropic.APIStatusError as exc:
            raise _status_error(exc) from exc

        self.last_model = message.model
        usage = message.usage
        return ExpertTurn(
            content=[block.to_dict() for block in message.content],
            stop_reason=message.stop_reason,
            model=message.model,
            usage=ExpertUsage(
                input_tokens=usage.input_tokens or 0,
                output_tokens=usage.output_tokens or 0,
                cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", None) or 0,
                cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", None) or 0,
                model=message.model,
            ),
        )


def _status_error(exc: "anthropic.APIStatusError") -> Exception:
    detail = f"HTTP {exc.status_code} : {exc.message}"
    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return ExpertUnavailableError(f"Clé ANTHROPIC_API_KEY refusée par Claude ({detail}).")
    if exc.status_code == 429 or exc.status_code >= 500:
        return ExpertUnavailableError(f"Claude momentanément indisponible ({detail}).")
    if "credit balance" in str(exc.message).lower():
        return ExpertUnavailableError(f"Crédit Anthropic épuisé ({detail}).")
    return ExpertLLMError(f"Requête refusée par Claude ({detail}).")
