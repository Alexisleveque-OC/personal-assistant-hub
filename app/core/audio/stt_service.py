"""Transcription vocale (STT) par l'API Google Gemini : le texte seul, mot pour mot.

L'intention est comprise ensuite par l'agent à partir du texte : la transcription ne demande ni intention ni JSON
(un gros schéma ralentissait chaque dictée et la consigne de « corriger » faisait réécrire les propos).
"""
import base64
import logging
import re
import time
from typing import Any, Dict, Optional

import httpx

from app.core.llm.gemini_client import (
    GEMINI_API_BASE_URL,
    GeminiClient,
    get_gemini_client,
)
from app.core.audio.phonetic_normalizer import normalize_phonetics

logger = logging.getLogger(__name__)

# Marqueur demandé quand rien n'est dit : un modèle renvoie mal une réponse vide (mesuré le 18/11 sur du bruit :
# « 00:01 », un horodatage inventé).
NOTHING_SAID = "[rien]"
TRANSCRIPTION_PROMPT = (
    "Transcris mot pour mot, en français, ce qui est dit dans cet enregistrement. "
    "Ne corrige pas, ne reformule pas, ne réponds pas, n'ajoute ni horodatage ni description des sons : "
    "renvoie uniquement le texte prononcé, sans guillemets. "
    f"S'il n'y a aucune parole intelligible (silence, bruit, musique), renvoie exactement {NOTHING_SAID}"
)

# Horodatage seul (« 0:00 », « 00:01 ») : renvoyé malgré la consigne sur du bruit (mesuré le 18/11).
_NO_WORDS = re.compile(r"^[\d\s:.,;!?…'\"()\[\]-]*$")

NOTHING_HEARD_MESSAGE = "Je n'ai rien entendu de clair : rien n'a été envoyé. Réessaie ou tape ton message."

STT_USER_FAILURE_MESSAGE = (
    "Je n'ai pas pu transcrire ton message : quota Gemini atteint ou service surchargé. "
    "Réessaie dans un instant ou tape-le."
)

_HTTP_FAILURE_LABELS = {429: "quota atteint", 503: "surchargé", 404: "modèle introuvable", 400: "requête refusée"}


class STTUnavailableError(RuntimeError):
    """Aucun modèle n'a pu transcrire : le détail (modèle par modèle) va aux logs, `user_message` au téléphone."""

    def __init__(self, detail: str, user_message: str = STT_USER_FAILURE_MESSAGE) -> None:
        super().__init__(detail)
        self.user_message = user_message


def _describe_failure(exc: Exception) -> str:
    """Raison courte d'un échec, sans jamais reprendre l'URL appelée."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return f"{_HTTP_FAILURE_LABELS.get(status, 'erreur HTTP')} ({status})"
    if isinstance(exc, httpx.TimeoutException):
        return "délai dépassé"
    if isinstance(exc, httpx.HTTPError):
        return f"erreur réseau ({type(exc).__name__})"
    return f"réponse inexploitable ({type(exc).__name__}: {exc})"


class AudioSTTService:
    """Service de traitement direct des flux audio vers l'API multimodale Gemini."""

    def __init__(self, gemini_client: Optional[GeminiClient] = None) -> None:
        self.gemini_client = gemini_client or get_gemini_client()

    def build_multimodal_gemini_payload(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> Dict[str, Any]:
        """Payload Gemini : l'audio en base64 (inlineData) et la consigne de transcription, réponse en texte brut."""
        b64_audio = base64.b64encode(audio_bytes).decode("utf-8")

        # Nettoyage et normalisation du MIME type (suppression des paramètres ;codecs=opus etc.)
        clean_mime = (mime_type or "audio/webm").split(";")[0].strip().lower()
        if clean_mime in ("video/mp4", "audio/m4a", "audio/x-m4a", "audio/aac"):
            clean_mime = "audio/mp4"
        elif clean_mime in ("video/webm", "video/x-matroska"):
            clean_mime = "audio/webm"
        elif clean_mime in ("video/ogg",):
            clean_mime = "audio/ogg"

        return {
            "contents": [
                {
                    "parts": [
                        {"inlineData": {"mimeType": clean_mime, "data": b64_audio}},
                        {"text": TRANSCRIPTION_PROMPT},
                    ]
                }
            ],
            "generationConfig": {"temperature": 0.0, "response_mime_type": "text/plain"},
        }

    async def transcribe(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
        """Envoie l'audio à Gemini et retourne le texte transcrit (normalisation phonétique appliquée)."""
        if not self.gemini_client.is_configured:
            raise STTUnavailableError(
                "Clé GEMINI_API_KEY absente pour le STT audio.",
                user_message="Transcription impossible : la clé Gemini n'est pas configurée sur le serveur.",
            )

        if self.gemini_client.is_daily_quota_exceeded():
            raise STTUnavailableError(
                "Plafond journalier Gemini atteint pour le STT audio.",
                user_message="Je n'ai pas pu transcrire ton message : plafond journalier Gemini atteint. Tape-le en attendant.",
            )

        model_name = await self.gemini_client.resolve_model()
        candidates_to_try = [model_name]
        for cand in self.gemini_client.get_candidate_models():
            if cand not in candidates_to_try:
                candidates_to_try.append(cand)

        payload = self.build_multimodal_gemini_payload(audio_bytes, mime_type)
        per_model_timeout = min(self.gemini_client.timeout, 12.0)
        failures: list[str] = []

        for candidate_model in candidates_to_try:
            url = f"{GEMINI_API_BASE_URL}/models/{candidate_model}:generateContent"
            start_time = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=per_model_timeout) as http_client:
                    response = await http_client.post(
                        url, headers={"x-goog-api-key": self.gemini_client.api_key}, json=payload
                    )
                    if response.status_code == 429:
                        self.gemini_client.mark_model_temporarily_unavailable(candidate_model, 60.0)
                    response.raise_for_status()
                    data = response.json()

                latency_ms = (time.perf_counter() - start_time) * 1000
                self.gemini_client.record_request(latency_ms)
                self.gemini_client.set_active_working_model(candidate_model)

                candidates = data.get("candidates", [])
                if not candidates:
                    raise ValueError("Aucun candidat retourné par Gemini pour l'audio.")

                # Sans aucune partie de texte : rien d'audible, traité comme une transcription vide.
                parts = candidates[0].get("content", {}).get("parts", [])
                transcription = "".join(part.get("text", "") for part in parts).strip().strip('"«»').strip()
                break
            except Exception as exc:
                failures.append(f"{candidate_model} : {_describe_failure(exc)}")
                continue
        else:
            detail = "Échec de transcription audio sur tous les modèles : " + " ; ".join(failures)
            logger.error(detail)
            raise STTUnavailableError(detail)

        # Réponse vide : rien d'audible (bruit, silence). Ce n'est pas une panne : pas de repli sur un autre modèle.
        if transcription == NOTHING_SAID or _NO_WORDS.match(transcription):
            raise STTUnavailableError(f"Aucune parole transcrite par {candidate_model}.", user_message=NOTHING_HEARD_MESSAGE)
        return normalize_phonetics(transcription)


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
