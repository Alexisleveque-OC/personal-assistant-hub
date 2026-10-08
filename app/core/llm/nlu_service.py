"""Service NLU basé sur Google Gemini avec sorties structurées et repli déterministe."""
import json
import logging
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, List, Tuple
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


SYSTEM_PROMPT = """Tu es Otis, le scribe et assistant personnel complice d'Alexis.
Ta mission est d'analyser la requête utilisateur (orale ou écrite) et d'extraire l'intention et ses paramètres avec bon sens, précision, intelligence et bienveillance.

Liste des intentions disponibles :
1. get_meal_plan : consulter le menu prévu. Paramètres optionnels : "period" (soir, midi, demain, jour, prochain), "day_name" (Lundi, etc.), "target_date" (JJ/MM/AAAA). Si la requête mentionne ce soir ou aujourd'hui, privilégie period="soir" (ou "midi" si midi).
2. get_recipe_ingredients : demander les ingrédients d'une recette. Paramètre : "recipe" (nom du plat).
3. add_recipe_ingredients : ajouter les ingrédients d'une recette aux courses. Paramètres : "recipe", "exclude" (ingrédients exclus), "include".
4. set_meal_plan : planifier ou changer un repas. Paramètres : "meal" (nom du plat), "period" (midi, soir), "day_name", "target_date".
5. add_shopping_item : ajouter un ou plusieurs articles aux courses (ex: "j'ai besoin d'acheter des mandarines", "on a plus de sopalin", "pense au beurre", "prends du steak").
   Paramètres :
   - "item" : nom de l'article nettoyé (ex: 'mandarines').
   - "items" : liste de noms si plusieurs articles sont cités.
   - "rayon" : Si le contexte contient "available_rayons", déduis avec bon sens le rayon exact le plus évident parmi cette liste (ex: mandarines -> 'Fruits', steak -> 'Boucherie', sopalin -> 'PQ + entretien', lessive -> 'PQ + entretien', saumon -> 'Poissonnerie').
   - "is_ambiguous" : true UNIQUEMENT si l'article est réellement hybride ou ambigu (ex: 'papier cuisson' qui peut être en Épicerie ou en Entretien). Pour un fruit, légume, viande, laitage ou produit ménager classique, is_ambiguous DOIT être false.
   - "suggested_options" : liste de 2 ou 3 rayons plausibles parmi available_rayons si is_ambiguous est true.
6. get_shopping_list : consulter la liste de courses. Paramètres optionnels : "filter" (waiting_list, current_week), "rayon", "status" (remaining, bought).
7. mark_shopping_bought : marquer des articles comme achetés. Paramètres : "items" ou "all": true.
8. clear_shopping_list : vider la liste de courses.
9. check_shopping_completion : vérifier si tout est coché.

10. Sport & Running (Mini-Coach Otis) :
   - get_sport_session : consulter la séance de running prévue ou réalisée (ex: "Qu'est-ce que j'ai comme séance aujourd'hui ?", "C'est quoi ma course de demain ?").
     Paramètres optionnels : "target_date" (today, demain, hier, ou date JJ/MM/AAAA), "period".
   - log_sport_session : enregistrer vocalement une séance terminée (ex: "J'ai couru 8 km en 42 minutes avec 120m de dénivelé, ressenti 6 sur 10", "J'ai fait 30 minutes de renfo, ressenti 7").
     Paramètres :
     - "distance_km" : float (ex: 8.0, 7.5, 10.2). Optionnel pour le renforcement musculaire.
     - "duration_seconds" : int (convertis la durée orale en secondes totales, ex: 42 min -> 2520, 30 min -> 1800).
     - "denivele_d_plus" : int en mètres (ex: 120, 80) si précisé.
     - "type_seance" : "EF", "Fractionné", "Sortie Longue", "Tempo", "Récup", "Renforcement".
     - "ressenti_rpe" : int de 1 à 10 (effort perçu).
     - "meteo_note" : int de 1 à 10 (difficulté météo si mentionnée).
     - "notes" : texte libre ou détails fractionné/renfo.
     - "target_date" : date de la séance si elle a eu lieu hier ou un autre jour.
   - update_sport_session : modifier a posteriori le ressenti (RPE), ajuster ou ajouter une note de douleur/périostite sur une séance passée (ex: "Otis, modifie le ressenti de ma course de dimanche à 9 sur 10 à cause de ma périostite", "Otis, ajoute une note sur ma course de dimanche : douleur au tibia à J+2", "Change le RPE d'hier à 8").
     Paramètres :
     - "target_date" : date ou jour ciblé (ex: "dimanche", "hier", "2026-10-04").
     - "ressenti_rpe" : int de 1 à 10 si mentionné.
     - "notes" : note ou commentaire sur la douleur / périostite / ressenti.
     - "append_notes" : true si l'utilisateur demande d'ajouter ou compléter une note existante.
   - get_sport_weekly_summary : consulter le bilan hebdomadaire et les conseils de sécurité d'Otis (ex: "J'en suis à combien de kilomètres cette semaine ?", "Quel est mon bilan de running ?", "Combien je peux courir la semaine prochaine ?").
     Paramètres : "week_num" (int), "year" (int).
   - plan_sport_session : planifier une future séance (ex: "Planifie-moi un fractionné jeudi", "Prévois 12 km dimanche", "Prévois 30 minutes de renfo vendredi").
     Paramètres : "target_date", "day_name", "type_seance", "distance_km", "notes".
   - plan_weekly_training : générer proactivement le plan d'entraînement pour toute la semaine (ex: "Otis, prévois-moi ma semaine d'entraînement", "Que me conseilles-tu cette semaine ?", "Planifie ma semaine de running", "Otis, je voudrais faire 15 km samedi, prévois ma semaine", "Prévois une semaine de repos").
     Paramètres : "week_num" (int), "year" (int), "is_deload" (bool), "user_wishes" (string).

11. get_budget_balance : solde financier. Paramètre : "category" (courses, loisir, general).
12. log_expense : enregistrer une dépense. Paramètres : "amount" (float), "category".
13. add_task : ajouter un rappel/tâche. Paramètre : "task".
14. list_tasks : lister les tâches.
15. summarize_emails : résumer les emails importants.
16. toggle_device : domotique. Paramètres : "device", "action" ("on", "off").
17. small_talk : salutations, politesse, humeur. Fournis une phrase courte, sympa et complice dans "conversational_reply" (l'esprit d'Otis le scribe).
18. confirm / cancel : oui, d'accord, non, annuler.
19. choose_rayon : réponse à une clarification de rayon pour un article (ex: "En entretien", "Épicerie", "Laisse en divers", "Rayon frais"). Paramètres : "rayon" (nom du rayon).

20. Second Cerveau & Notes compartimentées (Phase 6) :
   - save_note : capturer et classifier instantanément une note ou idée dans le second cerveau.
     Paramètres :
     - "content" : contenu principal épuré de la note.
     - "category" : segment thématique de la note.
       * Les 5 segments fondamentaux par défaut sont :
         - "dev_idea" : idées de développement, code, features (« À dev », « Idée de code »)
         - "bug_report" : anomalies, bugs à corriger (« Bug », « Correction », « Problème sur... »)
         - "thought" : pensées libres, inspirations, réflexions (« Idée pour plus tard », « Note libre »)
         - "preference" : préférences, goûts, habitudes de vie (« J'aime... », « Je préfère... »)
         - "task" : tâches concrètes (« Tâche », « Penser à... »)
       * Segments dynamiques auto-découverts : Otis est autonome et adaptable ! Si un mot-clé, préfixe ou concept revient régulièrement ou si la note porte sur un domaine distinct (ex: "voyage", "finance", "lecture", "musique", "cuisine", "maison", "santé", etc.), crée et affecte directement ce segment personnalisé dans "category".
     - "tags" : liste de mots-clés optionnels.
   - list_notes : consulter les notes du second cerveau. Paramètres optionnels : "category" (dev_idea, bug_report, voyage, etc.), "status".
   - delete_note : supprimer une note par son identifiant. Paramètre : "note_id" (int).


21. unknown : quand la requête n'est pas une commande directe, ou si elle est floue, incomplète, interrogative ou réflexive.
    RÈGLE MAJEURE D'INTELLIGENCE : Ne réponds JAMAIS par un message générique froid. Analyse le besoin sous-jacent et génère dans "conversational_reply" une réponse complice, intelligente et concise qui aide Alexis.

RÈGLES DE STYLE ET CONCISION (OBLIGATOIRE) :
- Sois très concis : MAXIMUM 1 à 2 phrases courtes et directes.
- Évite les formules de politesse creuses et les flatteries inutiles. Va droit au fait avec l'esprit vif et complice d'Otis.

CONTINUITÉ DU DIALOGUE (CONTEXTE ET MÉMOIRE) :
- Utilise l'historique des échanges récents pour maintenir le fil de la discussion. Ne redemande jamais ce qui a déjà été dit.
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
                "is_ambiguous": {"type": "BOOLEAN"},
                "suggested_options": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
                "status": {"type": "STRING"},
                "all": {"type": "BOOLEAN"},
                "category": {"type": "STRING"},
                "amount": {"type": "NUMBER"},
                "task": {"type": "STRING"},
                "device": {"type": "STRING"},
                "action": {"type": "STRING"},
                # Paramètres Second Cerveau (Phase 6)
                "content": {"type": "STRING"},
                "note_id": {"type": "INTEGER"},
                "tags": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                },
                # Paramètres Sport & Running (Otis)
                "distance_km": {"type": "NUMBER"},
                "duration_seconds": {"type": "INTEGER"},
                "duration": {"type": "STRING"},
                "denivele_d_plus": {"type": "INTEGER"},
                "type_seance": {"type": "STRING"},
                "ressenti_rpe": {"type": "INTEGER"},
                "meteo_note": {"type": "INTEGER"},
                "notes": {"type": "STRING"},
                "append_notes": {"type": "BOOLEAN"},
                "week_num": {"type": "INTEGER"},
                "year": {"type": "INTEGER"},
                "is_deload": {"type": "BOOLEAN"},
                "user_wishes": {"type": "STRING"},
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

        now = datetime.now()
        today = now.date()
        weekdays = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
        current_day_name = weekdays[today.weekday()].capitalize()

        user_content = f"Date courante : {current_day_name} {today.strftime('%d/%m/%Y')} (ISO: {today.isoformat()})\n"
        history = context.get("history", []) if context else []
        other_context = {k: v for k, v in context.items() if k != "history"} if context else {}

        if history and isinstance(history, list):
            user_content += "Historique des échanges récents :\n"
            for turn in history[-6:]:
                if isinstance(turn, dict):
                    role = "Alexis" if turn.get("role") == "user" else "Assistant"
                    user_content += f"- {role} : \"{turn.get('text', '')}\"\n"
            user_content += "\n"

        user_content += f"Requête actuelle d'Alexis : \"{query}\""
        if other_context:
            user_content += f"\nContexte système : {json.dumps(other_context, ensure_ascii=False, default=str)}"

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
        per_model_timeout = min(self.gemini_client.timeout, 5.0)

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
                        logger.info(
                            f"Modèle {candidate_model} temporairement indisponible ({response.status_code}), bascule sur le candidat suivant."
                        )
                        continue
                    response.raise_for_status()
                    data = response.json()

                latency_ms = (time.perf_counter() - start_time) * 1000
                self.gemini_client.record_request(latency_ms)
                self.gemini_client.set_active_working_model(candidate_model)

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
                params = dict(structured_resp.parameters)
                if "target_date" in params and isinstance(params["target_date"], str):
                    raw_td = params["target_date"].strip().lower()
                    if raw_td in ("today", "ce soir", "ce midi", "aujourd'hui", "aujourdhui", "ce jour"):
                        params["target_date"] = today.strftime("%d/%m/%Y")
                        if not params.get("period"):
                            params["period"] = "soir" if "soir" in query.lower() else ("midi" if "midi" in query.lower() else "jour")
                    elif raw_td in ("tomorrow", "demain"):
                        params["target_date"] = (today + timedelta(days=1)).strftime("%d/%m/%Y")
                        if not params.get("period"):
                            params["period"] = "demain"

                return ParsedIntent(
                    intent=structured_resp.intent,
                    confidence=structured_resp.confidence,
                    parameters=params,
                    raw_query=query,
                    conversational_reply=structured_resp.conversational_reply,
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


def _fallback_infer_rayon(item_name: str, available_rayons: List[str]) -> Tuple[str, Optional[List[str]]]:
    """Fallback heuristique local intelligent en cas d'absence de LLM."""
    import unicodedata
    norm = "".join(
        c for c in unicodedata.normalize("NFKD", item_name.lower())
        if not unicodedata.combining(c)
    )

    # 1. Fruits & Légumes
    if any(w in norm for w in [
        "mandarine", "clementine", "orange", "pomme", "poire", "banane", "citron", "fraise",
        "salade", "tomate", "courgette", "carotte", "poireau", "oignon", "ail", "avocat",
        "haricot", "champignon", "patate", "legume", "fruit", "peche", "abricot"
    ]):
        for r in available_rayons:
            if "fruit" in r.lower() or "legume" in r.lower():
                return r, None

    # 2. Boucherie / Poissonnerie
    if any(w in norm for w in ["poulet", "boeuf", "porc", "steak", "escalope", "dinde", "viande", "jambon", "saumon", "thon"]):
        for r in available_rayons:
            if "bouch" in r.lower() or "viande" in r.lower() or "frais" in r.lower():
                return r, None

    # 3. Entretien
    if any(w in norm for w in ["lessive", "eponge", "liquide vaisselle", "pq", "papier toilette", "sac poubelle", "javel", "nettoyant", "sopalin"]):
        for r in available_rayons:
            if "entretien" in r.lower() or "pq" in r.lower():
                return r, None

    # 4. Hygiène
    if any(w in norm for w in ["shampoing", "savon", "dentifrice", "douche", "coton", "brosse"]):
        for r in available_rayons:
            if "hygiene" in r.lower():
                return r, None

    # 5. Cas d'ambiguïté réelle (ex: papier cuisson, alu)
    if "cuisson" in norm or "alu" in norm:
        opts = [r for r in available_rayons if "entretien" in r.lower() or "epicerie" in r.lower()]
        return "Entretien", opts if len(opts) >= 2 else ["Entretien", "Épicerie"]

    return "Divers", None


async def infer_rayon_with_llm(
    item_name: str,
    available_rayons: List[str],
    gemini_client: Optional[GeminiClient] = None,
) -> Tuple[str, Optional[List[str]]]:
    """Déduit intelligemment le rayon d'un article grâce à Gemini, avec détection d'ambiguïté réelle."""
    safe_rayons = [r for r in available_rayons if isinstance(r, str)] if isinstance(available_rayons, (list, tuple)) else []
    client = gemini_client or get_gemini_client()
    if not client.api_key or client.is_daily_quota_exceeded() or not safe_rayons:
        return _fallback_infer_rayon(item_name, safe_rayons)

    prompt = (
        f"Tu es l'expert en organisation des courses du Personal Assistant Hub.\n"
        f"Article demandé : '{item_name}'.\n"
        f"Rayons disponibles dans le magasin : {json.dumps(safe_rayons, ensure_ascii=False)}.\n"
        f"Détermine le rayon le plus évident et exact parmi la liste fournie.\n"
        f"- Si le rayon est évident (ex: mandarines -> Fruits & Légumes, steak -> Boucherie, lessive -> Entretien, saumon -> Frais), "
        f"retourne 'rayon': <nom_exact_du_rayon>, 'is_ambiguous': false, 'suggested_options': null.\n"
        f"- Si et seulement si l'article est réellement hybride ou ambigu (ex: papier cuisson -> Entretien ou Épicerie), "
        f"retourne 'rayon': <nom_du_rayon_par_defaut>, 'is_ambiguous': true, 'suggested_options': [rayon1, rayon2].\n"
    )

    schema = {
        "type": "OBJECT",
        "properties": {
            "rayon": {"type": "STRING"},
            "is_ambiguous": {"type": "BOOLEAN"},
            "suggested_options": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
            },
        },
        "required": ["rayon", "is_ambiguous"],
    }

    candidates = client.get_candidate_models()
    for model_name in candidates:
        try:
            url = f"{GEMINI_API_BASE_URL}/models/{model_name}:generateContent?key={client.api_key}"
            payload = {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "responseMimeType": "application/json",
                    "responseSchema": schema,
                },
            }
            async with httpx.AsyncClient(timeout=1.8) as http_client:
                resp = await http_client.post(url, json=payload)
                if resp.status_code in (404, 503):
                    continue
                resp.raise_for_status()
                client.record_request()
                client.set_active_working_model(model_name)
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                res = json.loads(text)

                target_rayon = res.get("rayon", "Divers")
                # Trouver la correspondance exacte dans available_rayons
                for r in available_rayons:
                    if r.lower() == target_rayon.lower():
                        target_rayon = r
                        break

                is_ambig = bool(res.get("is_ambiguous", False))
                options = res.get("suggested_options") if is_ambig else None
                return target_rayon, options

        except Exception as exc:
            logger.warning(f"Erreur déduction de rayon Gemini sur {model_name} : {exc}")
            continue

    return _fallback_infer_rayon(item_name, available_rayons)
