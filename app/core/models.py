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
    CHECK_SHOPPING_COMPLETION = "check_shopping_completion"

    # Budget (Google Sheet 2)
    GET_BUDGET_BALANCE = "get_budget_balance"
    LOG_EXPENSE = "log_expense"

    # Sport & Running (Google Sheet 3 - Mini-Coach Otis)
    GET_SPORT_SESSION = "get_sport_session"
    LOG_SPORT_SESSION = "log_sport_session"
    GET_SPORT_WEEKLY_SUMMARY = "get_sport_weekly_summary"
    PLAN_SPORT_SESSION = "plan_sport_session"
    UPDATE_SPORT_SESSION = "update_sport_session"
    PLAN_WEEKLY_TRAINING = "plan_weekly_training"
    EXPLAIN_SPORT_EXERCISE = "explain_sport_exercise"

    # Google Tasks
    ADD_TASK = "add_task"
    LIST_TASKS = "list_tasks"

    # Gmail
    SUMMARIZE_EMAILS = "summarize_emails"

    # Domotique
    TOGGLE_DEVICE = "toggle_device"

    # Conversation / Politesse
    SMALL_TALK = "small_talk"

    # Confirmation interactive & clarifications
    CONFIRM = "confirm"
    CANCEL = "cancel"
    CHOOSE_RAYON = "choose_rayon"

    # Second Cerveau & Notes compartimentées (Phase 6)
    SAVE_NOTE = "save_note"
    LIST_NOTES = "list_notes"
    DELETE_NOTE = "delete_note"

    # Auto-Apprentissage Vocal (Phase 6)
    TEACH_ASSISTANT = "teach_assistant"

    # Non reconnu
    UNKNOWN = "unknown"




class ParsedIntent(BaseModel):
    """Résultat de l'analyse NLU d'une phrase utilisateur."""
    intent: IntentType
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    raw_query: str
    conversational_reply: Optional[str] = Field(
        default=None,
        description="Réponse intelligente et réfléchie générée par le LLM pour guider l'utilisateur ou dialoguer",
    )


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


class ConversationLogItem(BaseModel):
    """Représentation d'une interaction enregistrée dans le journal d'audit."""
    id: int
    session_id: Optional[str] = None
    raw_query: str
    intent: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    spoken_response: str
    success: bool
    latency_ms: float = 0.0
    llm_model: Optional[str] = None
    error_trace: Optional[str] = None
    created_at: Optional[str] = None


class ConversationLogsListResponse(BaseModel):
    """Réponse paginée pour la consultation des logs d'audit."""
    total: int
    limit: int
    offset: int
    items: list[ConversationLogItem]


class ConversationFeedbackCreate(BaseModel):
    """Payload pour enregistrer un retour ou une correction sur un échange."""
    feedback_type: str = Field(..., description="'positive', 'negative', 'correction'")
    user_note: Optional[str] = None


class ConversationFeedbackResponse(BaseModel):
    """Confirmation de création d'un feedback."""
    success: bool
    feedback_id: int


# ============================================================================
# Second Cerveau Compartimenté (Phase 6)
# ============================================================================

class NoteCategory(str, Enum):
    """Segments fondamentaux par défaut du Second Cerveau (extensibles dynamiquement)."""
    DEV_IDEA = "dev_idea"       # 🛠️ Idées de dev (« À dev », « J'aimerais que ça fasse... »)
    BUG_REPORT = "bug_report"   # 🐛 Corrections (« Bug », « Problème sur... »)
    THOUGHT = "thought"         # 💡 Pensées et notes libres (« Idée », « Réflexion »)
    PREFERENCE = "preference"   # 🎯 Préférences et habitudes de vie (« J'aime... », « Je préfère... »)
    TASK = "task"               # 📋 Tâches (« Tâche à faire », « Penser à... »)


class SecondBrainNoteItem(BaseModel):
    """Représentation d'une note stockée dans le Second Cerveau SQLite."""
    id: int
    category: str
    content: str
    tags: list[str] = Field(default_factory=list)
    status: str = "active"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SecondBrainNotesListResponse(BaseModel):
    """Réponse paginée pour la consultation des notes du Second Cerveau."""
    total: int
    limit: int
    offset: int
    items: list[SecondBrainNoteItem]


class NoteCreate(BaseModel):
    """Payload pour la création directe d'une note."""
    category: Optional[str] = NoteCategory.THOUGHT.value
    content: str
    tags: Optional[list[str]] = Field(default_factory=list)


class NoteUpdate(BaseModel):
    """Payload pour la mise à jour partielle d'une note."""
    category: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[list[str]] = None


# ============================================================================
# Auto-Apprentissage Vocal (user_learnings)
# ============================================================================

class UserLearningItem(BaseModel):
    """Règle personnalisée apprise par Otis."""
    id: int
    rule_text: str
    category: str = "general"
    original_error: Optional[str] = None
    correction: Optional[str] = None
    active: bool = True
    created_at: Optional[str] = None


class UserLearningsListResponse(BaseModel):
    """Liste paginée des règles apprises."""
    total: int
    limit: int
    offset: int
    items: list[UserLearningItem]


class LearningCreate(BaseModel):
    """Payload pour créer ou enregistrer une règle apprise."""
    rule_text: str
    category: Optional[str] = "general"
    original_error: Optional[str] = None
    correction: Optional[str] = None
    active: bool = True


class LearningUpdate(BaseModel):
    """Payload pour modifier une règle apprise (ex: désactiver)."""
    rule_text: Optional[str] = None
    category: Optional[str] = None
    original_error: Optional[str] = None
    correction: Optional[str] = None
    active: Optional[bool] = None




