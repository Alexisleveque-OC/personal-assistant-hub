"""Modèles de données Pydantic pour les intentions et interactions."""
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class IntentType(str, Enum):
    # Repas & Courses (Google Sheet 1)
    GET_MEAL_PLAN = "get_meal_plan"
    GET_RECIPE_INGREDIENTS = "get_recipe_ingredients"
    ADD_RECIPE_INGREDIENTS = "add_recipe_ingredients"
    SET_MEAL_PLAN = "set_meal_plan"
    ADD_SHOPPING_ITEM = "add_shopping_item"
    GET_SHOPPING_LIST = "get_shopping_list"
    MARK_SHOPPING_BOUGHT = "mark_shopping_bought"
    CLEAR_SHOPPING_LIST = "clear_shopping_list"

    # Budget (Google Sheet 2)
    GET_BUDGET_BALANCE = "get_budget_balance"
    LOG_EXPENSE = "log_expense"

    # Google Tasks
    ADD_TASK = "add_task"
    LIST_TASKS = "list_tasks"

    # Gmail
    SUMMARIZE_EMAILS = "summarize_emails"

    # Domotique
    TOGGLE_DEVICE = "toggle_device"

    # Non reconnu
    UNKNOWN = "unknown"


class ParsedIntent(BaseModel):
    """Résultat de l'analyse NLU d'une phrase utilisateur."""
    intent: IntentType
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    raw_query: str


class InteractionRequest(BaseModel):
    """Requête entrante (texte ou transcription vocale)."""
    query: str = Field(..., min_length=1, description="Phrase ou commande en langage naturel")
    source: Optional[str] = Field(default="api", description="Origine: android, alexa, web, etc.")


class InteractionResponse(BaseModel):
    """Réponse retournée (pour affichage ou synthèse vocale TTS)."""
    success: bool
    spoken_response: str = Field(..., description="Texte formulé pour être lu à haute voix ou affiché")
    intent: ParsedIntent
    data: Optional[Dict[str, Any]] = None
