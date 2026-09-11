"""Point d'entrée principal de l'API Personal Assistant Hub."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.models import (
    InteractionRequest,
    InteractionResponse,
    IntentType,
    ParsedIntent,
)
from app.core.intent_parser import IntentParser

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Hub d'assistant personnel connecté à Google Sheets, Google Tasks, Gmail et Domotique.",
)

# CORS pour autoriser l'accès depuis une PWA, un widget ou un frontend local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from datetime import date, timedelta
import re
from typing import Optional

from app.connectors.sheets.meals_connector import (
    MealsShoppingConnector,
    DayMealPlanNotFoundError,
    RecipeNotFoundError,
)

intent_parser = IntentParser()

import logging

logger = logging.getLogger(__name__)

_meals_connector: Optional[MealsShoppingConnector] = None


def get_meals_connector() -> Optional[MealsShoppingConnector]:
    """Récupère l'instance active du connecteur de repas ou tente son initialisation."""
    global _meals_connector
    if _meals_connector is None:
        try:
            _meals_connector = MealsShoppingConnector()
        except Exception as exc:
            logger.warning(f"Impossible d'initialiser MealsShoppingConnector : {exc}")
            _meals_connector = None
    return _meals_connector


def set_meals_connector(connector: Optional[MealsShoppingConnector]) -> None:
    """Permet l'injection d'un connecteur (mock) pour les tests unitaires et d'intégration."""
    global _meals_connector
    _meals_connector = connector


_SESSIONS: dict[str, dict] = {}


def clear_sessions() -> None:
    """Réinitialise la mémoire de session (utilitaire pour les tests)."""
    _SESSIONS.clear()


@app.get("/", tags=["System"])
async def root():
    return {
        "app": settings.app_name,
        "version": "0.1.0",
        "status": "online",
        "docs": "/docs",
    }


@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "healthy",
        "environment": settings.app_env,
        "debug": settings.debug,
    }


@app.post("/api/v1/intent/parse", response_model=ParsedIntent, tags=["NLU"])
async def parse_intent(request: InteractionRequest):
    """Analyse la phrase en langage naturel et extrait l'intention et ses paramètres."""
    session_id = request.session_id or request.source or "default"
    session_ctx = _SESSIONS.setdefault(session_id, {})
    if request.context:
        session_ctx.update(request.context)
    return intent_parser.parse(request.query, context=session_ctx)


@app.post("/api/v1/interact", response_model=InteractionResponse, tags=["Interaction"])
async def interact(request: InteractionRequest):
    """Point d'entrée universel pour les requêtes vocales ou textuelles.
    
    1. Parse l'intention
    2. Route vers le connecteur approprié (MealsShoppingConnector, Tasks, etc.)
    3. Formule une réponse parlée / textuelle
    """
    session_id = request.session_id or request.source or "default"
    session_ctx = _SESSIONS.setdefault(session_id, {})
    if request.context:
        session_ctx.update(request.context)

    parsed = intent_parser.parse(request.query, context=session_ctx)
    connector = get_meals_connector()
    data = dict(parsed.parameters)

    match parsed.intent:
        case IntentType.GET_MEAL_PLAN:
            period = parsed.parameters.get("period", "soir")
            period_label = "ce soir" if period == "soir" else ("ce midi" if period == "midi" else period)
            if connector:
                try:
                    plan = connector.get_meal_plan(period=period)
                    dish = plan.dinner if period != "midi" and plan.dinner else (plan.lunch or "Rien de planifié")
                    spoken = f"D'après le planning des repas pour {period_label}, vous avez prévu : {dish}."
                    data["meal_plan"] = plan.model_dump()
                except DayMealPlanNotFoundError:
                    spoken = f"D'après le planning des repas pour {period_label}, aucun repas n'est encore programmé."
                except Exception as exc:
                    spoken = f"Impossible de récupérer le repas pour {period_label} : {exc}"
            else:
                spoken = f"D'après le planning des repas pour {period_label}, vous avez prévu : Lasagnes maison et salade verte."

        case IntentType.GET_RECIPE_INGREDIENTS:
            recipe_name = parsed.parameters.get("recipe", "")
            if connector:
                recipe = connector.get_recipe_ingredients(recipe_name)
                if recipe:
                    spoken = f"Pour préparer {recipe.name}, il vous faut : {', '.join(recipe.ingredients)}."
                    data["recipe"] = recipe.model_dump()
                    session_ctx["last_recipe"] = recipe.name
                else:
                    spoken = f"Désolé, je n'ai pas trouvé la recette '{recipe_name}' dans vos carnets de recettes."
            else:
                spoken = f"Pour préparer {recipe_name}, il vous faut les ingrédients standard."
                session_ctx["last_recipe"] = recipe_name

        case IntentType.ADD_RECIPE_INGREDIENTS:
            if parsed.parameters.get("error") == "no_context_recipe":
                spoken = "Je ne sais pas de quelle recette vous parlez. Demandez-moi d'abord la recette ou les ingrédients d'un plat !"
            else:
                recipe_name = parsed.parameters.get("recipe", "")
                exclude = parsed.parameters.get("exclude")
                exclude_items = [exclude] if exclude else None
                if connector:
                    try:
                        recipe, added = connector.add_recipe_ingredients_to_shopping_list(
                            recipe_name=recipe_name,
                            exclude_items=exclude_items,
                        )
                        excl_suffix = f" (hors {exclude})" if exclude else ""
                        spoken = f"J'ai ajouté les ingrédients de {recipe.name}{excl_suffix} à votre liste de courses ({len(added)} article(s) en attente)."
                        data["recipe"] = recipe.model_dump()
                        data["added_items"] = [it.model_dump() for it in added]
                        session_ctx["last_recipe"] = recipe.name
                    except RecipeNotFoundError:
                        spoken = f"Impossible d'ajouter les ingrédients : la recette '{recipe_name}' est introuvable."
                    except Exception as exc:
                        spoken = f"Erreur lors de l'ajout des ingrédients de '{recipe_name}' : {exc}"
                else:
                    excl_suffix = f" (hors {exclude})" if exclude else ""
                    spoken = f"J'ai ajouté les ingrédients de {recipe_name}{excl_suffix} à votre liste de courses."
                    session_ctx["last_recipe"] = recipe_name

        case IntentType.SET_MEAL_PLAN:
            meal = parsed.parameters.get("meal", "")
            period = parsed.parameters.get("period", "soir")
            target_date = date.today() + timedelta(days=1) if period == "demain" else date.today()
            if connector:
                try:
                    updated_plan = connector.set_meal_plan(
                        meal=meal,
                        target_date=target_date,
                        meal_type=period,
                    )
                    spoken = f"C'est noté, j'ai planifié {meal} pour {period}."
                    data["meal_plan"] = updated_plan.model_dump()
                except Exception as exc:
                    spoken = f"Impossible d'enregistrer le repas : {exc}"
            else:
                spoken = f"C'est noté, j'ai planifié {meal} pour {period}."

        case IntentType.ADD_SHOPPING_ITEM:
            item = parsed.parameters.get("item", "l'article")
            if connector:
                try:
                    added_item, warning = connector.add_shopping_item(item)
                    spoken = f"C'est noté, j'ai ajouté {item} à votre liste de courses."
                    if warning:
                        spoken += f" ({warning})"
                    data["item"] = added_item.model_dump()
                except Exception as exc:
                    spoken = f"Impossible d'ajouter {item} à la liste de courses : {exc}"
            else:
                spoken = f"C'est noté, j'ai ajouté {item} à votre liste de courses."

        case IntentType.GET_SHOPPING_LIST:
            if connector:
                try:
                    shopping = connector.get_shopping_list()
                    waiting_names = [it.item for it in shopping["waiting_list"]]
                    current_names = [it.name for it in shopping["current_week_items"]]
                    all_names = waiting_names + current_names
                    if all_names:
                        spoken = f"Voici les articles sur votre liste de courses : {', '.join(all_names)}."
                    else:
                        spoken = "Votre liste de courses est actuellement vide."
                    data["shopping_list"] = {
                        "waiting_list": [it.model_dump() for it in shopping["waiting_list"]],
                        "current_week_items": [it.model_dump() for it in shopping["current_week_items"]],
                    }
                except Exception as exc:
                    spoken = f"Impossible de lire la liste de courses : {exc}"
            else:
                spoken = "Voici les articles sur votre liste de courses : Pain, Pommes, Lait d'avoine."

        case IntentType.MARK_SHOPPING_BOUGHT:
            items_str = parsed.parameters.get("items", "")
            items_list = [i.strip() for i in re.split(r",|\bet\b", items_str) if i.strip()]
            if connector:
                try:
                    marked = connector.mark_shopping_items_bought(items_list)
                    spoken = f"C'est noté, j'ai coché comme acheté(s) : {', '.join(marked) if marked else items_str}."
                    data["marked"] = marked
                except Exception as exc:
                    spoken = f"Impossible de mettre à jour les achats : {exc}"
            else:
                spoken = f"C'est noté, j'ai coché comme acheté(s) : {items_str}."

        case IntentType.CLEAR_SHOPPING_LIST:
            if connector:
                try:
                    count = connector.clear_shopping_list(only_bought=True)
                    spoken = f"La liste de courses a été nettoyée ({count} article(s) acheté(s) supprimé(s))."
                    data["deleted_count"] = count
                except Exception as exc:
                    spoken = f"Impossible de nettoyer la liste de courses : {exc}"
            else:
                spoken = "La liste de courses a été nettoyée."

        case IntentType.GET_BUDGET_BALANCE:
            cat = parsed.parameters.get("category", "général")
            spoken = f"Il vous reste actuellement 145 euros sur votre budget {cat} pour ce mois."
        case IntentType.LOG_EXPENSE:
            amount = parsed.parameters.get("amount", 0)
            cat = parsed.parameters.get("category", "divers")
            spoken = f"C'est enregistré : {amount} euros ajoutés aux dépenses {cat}."
        case IntentType.ADD_TASK:
            task = parsed.parameters.get("task", "tâche")
            spoken = f"Tâche enregistrée dans Google Tasks : {task}."
        case IntentType.LIST_TASKS:
            spoken = "Vous avez 2 tâches aujourd'hui : Rappeler le garage et arroser les plantes."
        case IntentType.SUMMARIZE_EMAILS:
            spoken = "Vous avez 1 e-mail important de votre banque concernant un relevé mensuel."
        case IntentType.TOGGLE_DEVICE:
            device = parsed.parameters.get("device", "appareil")
            action = "allumée" if parsed.parameters.get("action") == "on" else "éteinte"
            spoken = f"La {device} a bien été {action}."
        case _:
            spoken = "Je n'ai pas bien compris votre demande. Pouvez-vous reformuler ?"

    return InteractionResponse(
        success=parsed.intent != IntentType.UNKNOWN and "error" not in parsed.parameters,
        spoken_response=spoken,
        intent=parsed,
        data=data,
    )
