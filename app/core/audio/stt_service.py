"""Service de reconnaissance vocale STT multimodal s'appuyant sur l'API Google Gemini."""
import base64
import json
import logging
import time
from typing import Any, Dict, Optional, Tuple

import httpx

from app.core.models import IntentType, ParsedIntent
from app.core.llm.gemini_client import (
    GEMINI_API_BASE_URL,
    GeminiClient,
    get_gemini_client,
)
from app.core.llm.nlu_service import GEMINI_JSON_SCHEMA, get_nlu_service
from app.core.audio.phonetic_normalizer import normalize_phonetics

logger = logging.getLogger(__name__)

GEMINI_AUDIO_JSON_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "transcribed_text": {
            "type": "STRING",
            "description": "Transcription textuelle exacte et fidèle de la parole de l'utilisateur",
        },
        "intent": {
            "type": "STRING",
            "enum": [i.value for i in IntentType],
        },
        "confidence": {"type": "NUMBER"},
        "parameters": GEMINI_JSON_SCHEMA["properties"]["parameters"],
        "conversational_reply": {"type": "STRING"},
    },
    "required": ["transcribed_text", "intent", "parameters"],
}


class AudioSTTService:
    """Service de traitement direct des flux audio vers l'API multimodale Gemini."""

    def __init__(self, gemini_client: Optional[GeminiClient] = None) -> None:
        self.gemini_client = gemini_client or get_gemini_client()

    def build_multimodal_gemini_payload(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/webm",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Construit le payload Gemini contenant le bloc inlineData base64 et le prompt d'analyse."""
        b64_audio = base64.b64encode(audio_bytes).decode("utf-8")

        prompt_text = (
            "Tu es Otis. Écoute attentivement cet extrait audio enregistré par Alexis.\n"
            "1. Transcris fidèlement ses propos dans 'transcribed_text' en éliminant les confusions phonétiques courantes.\n"
            "2. Identifie l'intention et extrait tous les paramètres correspondants selon le schéma fourni.\n"
        )
        if context:
            prompt_text += f"\nContexte : {json.dumps(context, ensure_ascii=False, default=str)}"

        return {
            "contents": [
                {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": b64_audio,
                            }
                        },
                        {"text": prompt_text},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "response_mime_type": "application/json",
                "response_schema": GEMINI_AUDIO_JSON_SCHEMA,
            },
        }

    async def process_audio(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/webm",
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, ParsedIntent]:
        """Envoie l'audio à Gemini et retourne le texte transcrit normalisé ainsi que l'intention extraite."""
        if not self.gemini_client.is_configured:
            raise RuntimeError("Le service STT audio multimodal nécessite une clé GEMINI_API_KEY configurée.")

        if self.gemini_client.is_daily_quota_exceeded():
            raise RuntimeError("Plafond de requêtes journalières Gemini atteint pour le STT audio.")

        model_name = await self.gemini_client.resolve_model()
        candidates_to_try = [model_name]
        for cand in self.gemini_client.get_candidate_models():
            if cand not in candidates_to_try:
                candidates_to_try.append(cand)

        payload = self.build_multimodal_gemini_payload(audio_bytes, mime_type, context)
        per_model_timeout = min(self.gemini_client.timeout, 12.0)
        last_exception = None

        for candidate_model in candidates_to_try:
            url = f"{GEMINI_API_BASE_URL}/models/{candidate_model}:generateContent?key={self.gemini_client.api_key}"
            start_time = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=per_model_timeout) as http_client:
                    response = await http_client.post(url, json=payload)
                    if response.status_code == 429:
                        self.gemini_client.mark_model_temporarily_unavailable(candidate_model, 60.0)
                        continue
                    if response.status_code in (503, 404):
                        continue
                    response.raise_for_status()
                    data = response.json()

                latency_ms = (time.perf_counter() - start_time) * 1000
                self.gemini_client.record_request(latency_ms)
                self.gemini_client.set_active_working_model(candidate_model)

                candidates = data.get("candidates", [])
                if not candidates:
                    raise ValueError("Aucun candidat retourné par Gemini pour l'audio.")

                parts = candidates[0].get("content", {}).get("parts", [])
                if not parts:
                    raise ValueError("Contenu vide dans la réponse audio Gemini.")

                raw_text = parts[0].get("text", "{}")
                parsed_json = json.loads(raw_text)

                raw_transcription = parsed_json.get("transcribed_text", "")
                normalized_transcription = normalize_phonetics(raw_transcription)

                intent_val = parsed_json.get("intent", IntentType.UNKNOWN.value)
                try:
                    intent_enum = IntentType(intent_val)
                except ValueError:
                    intent_enum = IntentType.UNKNOWN

                parsed_intent = ParsedIntent(
                    intent=intent_enum,
                    confidence=float(parsed_json.get("confidence", 0.9)),
                    parameters=parsed_json.get("parameters", {}),
                    raw_query=normalized_transcription,
                    conversational_reply=parsed_json.get("conversational_reply"),
                )

                return normalized_transcription, parsed_intent

            except Exception as exc:
                last_exception = exc
                continue

        logger.error(f"Échec du traitement audio STT par Gemini : {last_exception}")
        raise RuntimeError(f"Échec de transcription audio : {last_exception}")


_stt_service: Optional[AudioSTTService] = None


def get_stt_service() -> AudioSTTService:
    """Fournit l'instance globale du service STT audio."""
    global _stt_service
    if _stt_service is None:
        _stt_service = AudioSTTService()
    return _stt_service


def set_stt_service(service: Optional[AudioSTTService]) -> None:
    """Permet l'injection d'un service (mock) pour les tests unitaires."""
    global _stt_service
    _stt_service = service
