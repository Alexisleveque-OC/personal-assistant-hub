"""Modèles de données Pydantic pour les intentions et interactions."""
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, model_validator, computed_field


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

    # Conversation / Politesse
    SMALL_TALK = "small_talk"

    # Confirmation interactive
    CONFIRM = "confirm"
    CANCEL = "cancel"

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
    query: str = Field(default="", description="Phrase ou commande en langage naturel")
    source: Optional[str] = Field(default="api", description="Origine: android, alexa, web, etc.")
    session_id: Optional[str] = Field(default=None, description="Identifiant unique de session ou utilisateur")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Contexte conversationnel additionnel")

    @model_validator(mode="before")
    @classmethod
    def resolve_aliases(cls, data: Any) -> Any:
        """Permet l'interopérabilité avec les apps mobiles en acceptant 'text', 'message', 'prompt', etc."""
        if isinstance(data, dict):
            if not data.get("query"):
                for alias in ["text", "message", "prompt", "q"]:
                    if data.get(alias):
                        data["query"] = data[alias]
                        break
        return data


class InteractionResponse(BaseModel):
    """Réponse retournée (pour affichage ou synthèse vocale TTS)."""
    success: bool
    spoken_response: str = Field(..., description="Texte formulé pour être lu à haute voix ou affiché")
    intent: ParsedIntent
    data: Optional[Dict[str, Any]] = None

    @computed_field
    @property
    def speech(self) -> str:
        """Alias pour les moteurs TTS Android et raccourcis vocaux."""
        return self.spoken_response

    @computed_field
    @property
    def text(self) -> str:
        """Alias pour les affichages texte simples / bulles de dialogue."""
        return self.spoken_response

