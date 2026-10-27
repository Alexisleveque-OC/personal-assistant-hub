"""Suggestion de 2 rayons plausibles pour un article inconnu, posée ensuite en question à l'utilisateur.

Gemini ne décide jamais du rayon : il propose, l'utilisateur choisit. Indisponible ou réponse inexploitable →
aucune suggestion (liste vide, avec un avertissement journalisé) et la question devient ouverte.
"""
import json
import logging
from typing import List, Optional, Protocol, Sequence

import httpx

from app.core.llm.gemini_client import GEMINI_API_BASE_URL, GeminiClient, get_gemini_client

logger = logging.getLogger(__name__)

SUGGESTIONS_COUNT = 2
_MAX_MODELS_TRIED = 2
_TIMEOUT_SECONDS = 4.0
_EXCLUDED = {"divers"}


class RayonSuggester(Protocol):
    async def __call__(self, article: str, rayons: Sequence[str]) -> List[str]: ...


class GeminiRayonSuggester:
    def __init__(self, client: Optional[GeminiClient] = None) -> None:
        self._client = client

    @property
    def client(self) -> GeminiClient:
        return self._client or get_gemini_client()

    async def __call__(self, article: str, rayons: Sequence[str]) -> List[str]:
        candidates = [r for r in rayons if r.strip().casefold() not in _EXCLUDED]
        client = self.client
        if len(candidates) < SUGGESTIONS_COUNT:
            logger.warning(f"Suggestion de rayon impossible pour « {article} » : moins de 2 rayons dans l'onglet Rayons.")
            return []
        if not client.is_configured or client.is_daily_quota_exceeded():
            logger.warning(f"Suggestion de rayon impossible pour « {article} » : Gemini non configuré ou quota atteint.")
            return []

        payload = {
            "contents": [{"role": "user", "parts": [{"text": (
                f"Article de courses : « {article} ». Propose les 2 rayons de magasin les plus plausibles pour le "
                f"ranger, du plus au moins probable, parmi : {json.dumps(candidates, ensure_ascii=False)}."
            )}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {"rayons": {"type": "ARRAY", "items": {"type": "STRING", "enum": candidates}}},
                    "required": ["rayons"],
                },
            },
        }
        for model in client.get_candidate_models()[:_MAX_MODELS_TRIED]:
            url = f"{GEMINI_API_BASE_URL}/models/{model}:generateContent"
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as http:
                    resp = await http.post(url, params={"key": client.api_key}, json=payload)
                if resp.status_code in (429, 503):
                    client.mark_model_temporarily_unavailable(model)
                    continue
                resp.raise_for_status()
                client.record_request()
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                return self._validated(article, json.loads(text).get("rayons", []), candidates)
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
                logger.warning(f"Suggestion de rayon Gemini en échec sur {model} pour « {article} » : {exc}")
        logger.warning(f"Suggestion de rayon impossible pour « {article} » : aucun modèle Gemini disponible.")
        return []

    @staticmethod
    def _validated(article: str, answer: Sequence[str], candidates: Sequence[str]) -> List[str]:
        by_key = {r.casefold(): r for r in candidates}
        picked = list(dict.fromkeys(by_key[a.casefold()] for a in answer if isinstance(a, str) and a.casefold() in by_key))
        if len(picked) < SUGGESTIONS_COUNT:
            logger.warning(f"Suggestion de rayon inexploitable pour « {article} » : {answer!r}.")
            return []
        return picked[:SUGGESTIONS_COUNT]


_suggester: Optional[RayonSuggester] = None


def get_rayon_suggester() -> RayonSuggester:
    return _suggester or GeminiRayonSuggester()


def set_rayon_suggester(suggester: Optional[RayonSuggester]) -> None:
    """Injection d'un suggesteur (ex. hors-ligne) pour les tests."""
    global _suggester
    _suggester = suggester
