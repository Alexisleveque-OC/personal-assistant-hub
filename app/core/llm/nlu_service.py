"""Service NLU basé sur Google Gemini avec sorties structurées et repli déterministe."""
import json
import logging
import time
from typing import Any, Dict, Optional
import httpx
from pydantic import BaseModel, Field

from app.core.models import IntentType, ParsedIntent
from app.core.intent_parser import IntentParser
from app.core.llm.gemini_client import (
    GEMINI_API_BASE_URL,
    GeminiClient,
    get_gemini_client,
)

logger = logging.getLogger(__name__)

_default_local_parser = IntentParser()


class LLMNLUResponse(BaseModel):
    """Modèle Pydantic décrivant le contrat de sortie structurée renvoyé par Gemini."""
    intent: IntentType
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    conversational_reply: Optional[str] = Field(
        default=None,
        description="Réponse polie et naturelle pour le small talk ou clarification",
    )


SYSTEM_PROMPT = """Tu es le moteur NLU d'un assistant personnel pour Alexis.
Ta mission est d'analyser la requête utilisateur (orale ou écrite) et d'extraire l'intention et ses paramètres avec précision.

Liste des intentions disponibles :
1. get_meal_plan : consulter le menu prévu. Paramètres optionnels : "period" (soir, midi, demain, jour, prochain), "day_name" (Lundi, etc.), "target_date" (JJ/MM/AAAA).
2. get_recipe_ingredients : demander les ingrédients d'une recette. Paramètre : "recipe" (nom du plat).
3. add_recipe_ingredients : ajouter les ingrédients d'une recette aux courses. Paramètres : "recipe", "exclude" (ingrédients exclus), "include".
4. set_meal_plan : planifier ou changer un repas. Paramètres : "meal" (nom du plat), "period" (midi, soir), "day_name", "target_date".
5. add_shopping_item : ajouter un ou plusieurs articles aux courses. Paramètre : "item" (nom de l'article nettoyé).
6. get_shopping_list : consulter la liste de courses. Paramètres optionnels : "filter" (waiting_list, current_week), "rayon", "status" (remaining, bought).
7. mark_shopping_bought : marquer des articles comme achetés. Paramètres : "items" ou "all": true.
8. clear_shopping_list : vider la liste de courses.
9. check_shopping_completion : vérifier si tout est coché.
10. get_budget_balance : solde financier. Paramètre : "category" (courses, loisir, general).
11. log_expense : enregistrer une dépense. Paramètres : "amount" (float), "category".
12. add_task : ajouter un rappel/tâche. Paramètre : "task".
13. list_tasks : lister les tâches.
14. summarize_emails : résumer les emails importants.
15. toggle_device : domotique. Paramètres : "device", "action" ("on", "off").
16. small_talk : salutations, politesse, humeur. Fournis une phrase courte et sympa dans "conversational_reply".
17. confirm / cancel : oui, d'accord, non, annuler.
18. choose_rayon : réponse à une clarification de rayon pour un article (ex: "En entretien", "Épicerie", "Laisse en divers", "Rayon frais"). Paramètres : "rayon" (nom du rayon).
19. unknown : si la phrase est totalement incompréhensible ou hors sujet.

Résolution d'anaphores :
Si la phrase dit "ajoute ses ingrédients" ou "mets-le à ce soir", utilise le contexte fourni pour déduire la recette ou l'élément mentionné.
"""

GEMINI_JSON_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "intent": {
            "type": "STRING",
            "enum": [i.value for i in IntentType],
        },
        "confidence": {"type": "NUMBER"},
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "meal": {"type": "STRING"},
                "recipe": {"type": "STRING"},
                "item": {"type": "STRING"},
                "items": {"type": "STRING"},
                "period": {"type": "STRING"},
                "day_name": {"type": "STRING"},
                "target_date": {"type": "STRING"},
                "exclude": {"type": "STRING"},
                "include": {"type": "STRING"},
                "filter": {"type": "STRING"},
                "rayon": {"type": "STRING"},
                "status": {"type": "STRING"},
                "all": {"type": "BOOLEAN"},
                "category": {"type": "STRING"},
                "amount": {"type": "NUMBER"},
                "task": {"type": "STRING"},
                "device": {"type": "STRING"},
                "action": {"type": "STRING"},
            },
        },
        "conversational_reply": {"type": "STRING"},
    },
    "required": ["intent", "parameters"],
}


class GeminiNLUService:
    """Service d'analyse d'intentions NLU s'appuyant sur l'API Gemini avec fallback déterministe."""

    def __init__(
        self,
        gemini_client: Optional[GeminiClient] = None,
        fallback_parser: Optional[Any] = None,
    ) -> None:
        self.gemini_client = gemini_client or get_gemini_client()
        self.fallback_parser = fallback_parser or _default_local_parser

    async def parse(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ParsedIntent:
        """Analyse une requête utilisateur avec Gemini ou bascule sur le parseur local."""
        # 1. Vérification du quota et de la configuration
        if not self.gemini_client.is_configured:
            logger.debug("Gemini non configuré, utilisation du parseur local déterministe.")
            return self.fallback_parser.parse(query, context=context)

        if self.gemini_client.is_daily_quota_exceeded():
            logger.warning(
                "Plafond de requêtes journalières atteint pour Gemini. Bascule sur le parseur local."
            )
            return self.fallback_parser.parse(query, context=context)

        # 2. Appel à l'API Gemini avec Structured Outputs
        model_name = await self.gemini_client.resolve_model()
        candidates_to_try = [model_name]
        for cand in self.gemini_client.get_candidate_models():
            if cand not in candidates_to_try:
                candidates_to_try.append(cand)

        user_content = f"Requête : \"{query}\""
        if context:
            user_content += f"\nContexte actuel de la session : {json.dumps(context, ensure_ascii=False)}"

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": SYSTEM_PROMPT},
                        {"text": user_content},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "response_mime_type": "application/json",
                "response_schema": GEMINI_JSON_SCHEMA,
            },
        }

        last_exception = None
        for candidate_model in candidates_to_try:
            url = f"{GEMINI_API_BASE_URL}/models/{candidate_model}:generateContent?key={self.gemini_client.api_key}"
            start_time = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=self.gemini_client.timeout) as http_client:
                    response = await http_client.post(url, json=payload)
                    if response.status_code in (503, 404):
                        logger.info(
                            f"Modèle {candidate_model} temporairement indisponible ({response.status_code}), bascule sur le candidat suivant."
                        )
                        continue
                    response.raise_for_status()
                    data = response.json()

                latency_ms = (time.perf_counter() - start_time) * 1000
                self.gemini_client.record_request(latency_ms)
                self.gemini_client.set_resolved_model(candidate_model)

                # Extraction du JSON généré
                candidates = data.get("candidates", [])
                if not candidates:
                    raise ValueError("Aucun candidat retourné par Gemini")

                parts = candidates[0].get("content", {}).get("parts", [])
                if not parts:
                    raise ValueError("Aucune partie de texte dans le candidat Gemini")

                raw_text = parts[0].get("text", "{}")
                parsed_json = json.loads(raw_text)
                structured_resp = LLMNLUResponse.model_validate(parsed_json)

                # Conversion en ParsedIntent compatible avec le reste du projet
                return ParsedIntent(
                    intent=structured_resp.intent,
                    confidence=structured_resp.confidence,
                    parameters=structured_resp.parameters,
                    raw_query=query,
                )

            except Exception as exc:
                last_exception = exc
                continue

        logger.warning(
            f"Échec de l'analyse NLU Gemini ({last_exception}). "
            f"Bascule transparente sur le parseur local déterministe."
        )
        return self.fallback_parser.parse(query, context=context)


_nlu_service: Optional[GeminiNLUService] = None


def get_nlu_service() -> GeminiNLUService:
    """Fournit l'instance globale du service NLU."""
    global _nlu_service
    if _nlu_service is None:
        _nlu_service = GeminiNLUService()
    return _nlu_service


def set_nlu_service(service: Optional[GeminiNLUService]) -> None:
    """Permet l'injection d'un service (mock) pour les tests."""
    global _nlu_service
    _nlu_service = service
