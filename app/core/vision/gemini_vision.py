"""Appel Gemini Vision commun aux imports par capture : image + consigne → JSON conforme au schéma.

Meilleurs modèles d'abord (relais au suivant sur quota ou panne), clé en en-tête `x-goog-api-key` (jamais dans l'URL).
"""
import base64
import json
import logging
from typing import Any, Dict, List

import httpx

from app.core.llm.gemini_client import GEMINI_API_BASE_URL, GeminiClient

logger = logging.getLogger(__name__)

FALLBACK_VISION_MODELS = (
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
)
_DEPRECATED = ("2.5", "1.5", "2.0")  # versions retirées (404)


class VisionServiceUnavailableError(RuntimeError):
    """Gemini Vision est inaccessible (clé absente, quota, modèles indisponibles)."""


async def _models(client: GeminiClient) -> List[str]:
    candidates = await client.premium_candidate_models() if hasattr(client, "premium_candidate_models") else []
    ordered: List[str] = []
    for model in [*candidates, *FALLBACK_VISION_MODELS]:
        clean = model.replace("models/", "").strip()
        if clean and clean not in ordered and not any(old in clean for old in _DEPRECATED):
            ordered.append(clean)
    return ordered


async def generate_vision_json(
    client: GeminiClient, image_bytes: bytes, mime_type: str, prompt: str, schema: Dict[str, Any], tag: str,
) -> Dict[str, Any]:
    """Réponse JSON du premier modèle qui répond ; VisionServiceUnavailableError (modèles et codes cités) sinon."""
    if not client or not client.api_key:
        raise VisionServiceUnavailableError(
            "Analyse de capture impossible : aucune clé GEMINI_API_KEY n'est configurée sur le serveur."
        )
    payload = {
        "contents": [{"parts": [
            {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(image_bytes).decode("utf-8")}},
            {"text": prompt},
        ]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema, "temperature": 0.1},
    }
    failures: List[str] = []
    async with httpx.AsyncClient(timeout=25.0) as http_client:
        for model_name in await _models(client):
            url = f"{GEMINI_API_BASE_URL}/models/{model_name}:generateContent"
            try:
                resp = await http_client.post(url, headers={"x-goog-api-key": client.api_key}, json=payload)
            except Exception as exc:
                logger.warning(f"[{tag}] Échec appel {model_name} : {exc}")
                failures.append(f"{model_name} ({type(exc).__name__}: {exc})")
                continue
            if resp.status_code == 200:
                cands = resp.json().get("candidates", [])
                if not cands:
                    failures.append(f"{model_name} (réponse sans candidat)")
                    continue
                return json.loads(cands[0].get("content", {}).get("parts", [{}])[0].get("text", ""))
            if resp.status_code in (429, 503) and hasattr(client, "mark_model_temporarily_unavailable"):
                client.mark_model_temporarily_unavailable(model_name, 30.0)
            logger.warning(f"[{tag}] Modèle {model_name} erreur ({resp.status_code}): {resp.text[:150]}")
            failures.append(f"{model_name} ({resp.status_code})")
    raise VisionServiceUnavailableError("Tous les modèles Gemini Vision ont échoué : " + ", ".join(failures))
