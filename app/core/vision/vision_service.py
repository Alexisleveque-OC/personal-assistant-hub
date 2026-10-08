"""Service multimodal d'analyse visuelle de captures d'écran et photos pour le Second Cerveau."""
import base64
import json
import logging
from typing import Any, Dict, Optional

import httpx

from app.core.models import SecondBrainImageAnalysisResult
from app.core.llm.gemini_client import (
    GEMINI_API_BASE_URL,
    GeminiClient,
    get_gemini_client,
)

logger = logging.getLogger(__name__)

GEMINI_VISION_JSON_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "category": {
            "type": "STRING",
            "description": (
                "Catégorie cible la plus pertinente. Exemples fondamentaux : "
                "'bug_report' (erreur console, exception, bug UI), "
                "'dev_idea' (feature tech, repo GitHub, maquette, architecture), "
                "'voyage' ou 'vacances' (hôtel, vol, itinéraire, excursion), "
                "'cuisine' (recette, plat, ingrédients), "
                "'task' (liste de choses à faire, facture, document à traiter), "
                "'preference' (produit aimé, équipement running préféré), "
                "'thought' (citation, idée générale)."
            ),
        },
        "title": {
            "type": "STRING",
            "description": "Titre clair et concis (1 ligne) identifiant le contenu de l'image",
        },
        "summary": {
            "type": "STRING",
            "description": "Synthèse détaillée et immédiatement exploitable du contenu extrait (texte à l'écran, interface, points clés)",
        },
        "tags": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "Mots-clés / tags pertinents extraits de l'image (3 à 6 tags)",
        },
        "suggested_action": {
            "type": "STRING",
            "description": "Action concrète ou étape suivante suggérée",
        },
    },
    "required": ["category", "title", "summary", "tags"],
}


class VisionService:
    """Service d'analyse d'images s'appuyant sur l'API multimodale de Google Gemini."""

    def __init__(self, gemini_client: Optional[GeminiClient] = None) -> None:
        self.gemini_client = gemini_client or get_gemini_client()

    def build_vision_payload(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
        user_caption: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Construit le payload Gemini avec l'image en base64 inlineData et les consignes d'extraction."""
        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        prompt_text = (
            "Tu es Otis, l'assistant personnel et second cerveau d'Alexis.\n"
            "Alexis vient de t'envoyer cette image ou capture d'écran pour la mémoriser sans avoir à la décrire en détail.\n"
            "1. Analyse attentivement l'image (texte à l'écran, codes d'erreur, interfaces, éléments visuels, paysages, documents).\n"
            "2. Identifie précisément le sujet et classe-le dans la catégorie adéquate :\n"
            "   - 'bug_report' s'il s'agit d'un bug de code, exception, erreur terminal ou UI défaillante.\n"
            "   - 'dev_idea' s'il s'agit d'une idée de développement, composant, repo GitHub ou architecture.\n"
            "   - 'voyage' / 'vacances' pour des hôtels, destinations, vols ou locations.\n"
            "   - 'cuisine' pour des recettes, cartes de restaurant ou plats.\n"
            "   - 'task' pour des factures, rappels ou documents nécessitant une action.\n"
            "   - ou toute autre catégorie thématique naturelle.\n"
            "3. Rédige un titre percutant et un résumé synthétique très clair, avec des tags pertinents.\n"
        )

        if user_caption:
            prompt_text += f"\nNote / légende ajoutée par Alexis : « {user_caption} »\n"

        return {
            "contents": [
                {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": b64_image,
                            }
                        },
                        {"text": prompt_text},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                "responseSchema": GEMINI_VISION_JSON_SCHEMA,
            },
        }

    def analyze_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
        user_caption: Optional[str] = None,
    ) -> SecondBrainImageAnalysisResult:
        """Envoie l'image à Gemini Vision et retourne le résultat structuré."""
        return _call_gemini_vision(image_bytes, mime_type, user_caption, self.gemini_client)


def _call_gemini_vision(
    image_bytes: bytes,
    mime_type: str = "image/png",
    user_caption: Optional[str] = None,
    gemini_client: Optional[GeminiClient] = None,
) -> SecondBrainImageAnalysisResult:
    """Fonction isolée d'appel réseau à Gemini Vision."""
    client = gemini_client or get_gemini_client()
    if not client.api_key:
        logger.warning("[VisionService] Clé API Gemini absente, fallback heuristique local.")
        return _fallback_local_vision(user_caption)

    service = VisionService(gemini_client=client)
    payload = service.build_vision_payload(image_bytes, mime_type, user_caption)
    model_name = getattr(client, "_resolved_model", None) or getattr(client, "configured_model", "gemini-2.5-flash")
    if not model_name or model_name.lower() == "auto":
        model_name = "gemini-2.5-flash"
    url = f"{GEMINI_API_BASE_URL}/models/{model_name}:generateContent?key={client.api_key}"

    try:
        with httpx.Client(timeout=25.0) as http_client:
            resp = http_client.post(url, json=payload)

        if resp.status_code != 200:
            logger.error(f"[VisionService] Erreur Gemini API {resp.status_code}: {resp.text}")
            return _fallback_local_vision(user_caption)

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return _fallback_local_vision(user_caption)

        part = candidates[0].get("content", {}).get("parts", [{}])[0]
        raw_text = part.get("text", "{}")
        parsed = json.loads(raw_text)

        return SecondBrainImageAnalysisResult(
            category=parsed.get("category", "thought").lower(),
            title=parsed.get("title", "Image capturée"),
            summary=parsed.get("summary", "Contenu extrait de la capture."),
            tags=parsed.get("tags", ["image"]),
            suggested_action=parsed.get("suggested_action"),
        )
    except Exception as exc:
        logger.warning(f"[VisionService] Exception lors de l'appel Gemini Vision : {exc}")
        return _fallback_local_vision(user_caption)


def _fallback_local_vision(user_caption: Optional[str] = None) -> SecondBrainImageAnalysisResult:
    """Secours local si Gemini est indisponible."""
    caption_lower = (user_caption or "").lower()
    cat = "thought"
    if any(k in caption_lower for k in ["bug", "erreur", "crash", "fix"]):
        cat = "bug_report"
    elif any(k in caption_lower for k in ["dev", "code", "feature", "projet"]):
        cat = "dev_idea"
    elif any(k in caption_lower for k in ["hotel", "voyage", "vol", "vacance"]):
        cat = "voyage"

    return SecondBrainImageAnalysisResult(
        category=cat,
        title=user_caption or "Capture enregistrée",
        summary=f"Capture d'écran mémorisée avec la note : {user_caption or 'Sans description'}",
        tags=["image", cat],
        suggested_action="Examiner les détails de la capture ultérieurement.",
    )


def analyze_image_for_second_brain(
    image_bytes: bytes,
    mime_type: str = "image/png",
    user_caption: Optional[str] = None,
) -> SecondBrainImageAnalysisResult:
    """Point d'entrée principal pour analyser une capture/photo."""
    return _call_gemini_vision(image_bytes, mime_type, user_caption)


_vision_service_instance: Optional[VisionService] = None


def get_vision_service() -> VisionService:
    """Fournit le singleton du service de vision."""
    global _vision_service_instance
    if _vision_service_instance is None:
        _vision_service_instance = VisionService()
    return _vision_service_instance
