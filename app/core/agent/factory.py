"""Assemblage de l'agent pour une requête : outils sport (SQLite), planning hebdo, repas & courses, agenda, tâches, budget, notes,
LLM Gemini et, si configuré, expert Claude (cerveau en cascade, Phase 6.10)."""
import logging
from typing import Any, Optional, Sequence

from app.config import settings
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.agent_service import AgentService, ConversationTurn
from app.core.agent.errors import AgentUnavailableError
from app.core.agent.llm import AgentLLM, GeminiAgentLLM
from app.core.agent.tool_registry import ToolRegistry
from app.core.agent.tools.budget_registry import budget_tool_definitions
from app.core.agent.tools.budget_pending import get_pending_category_questions
from app.core.agent.tools.budget_tools import BudgetTools
from app.core.agent.tools.calendar_registry import calendar_tool_definitions
from app.core.agent.tools.calendar_tools import CalendarTools
from app.core.agent.tools.tasks_registry import tasks_tool_definitions
from app.core.agent.tools.tasks_tools import TasksTools
from app.core.agent.tools.meals_registry import meals_tool_definitions
from app.core.agent.tools.meals_tools import MealsTools
from app.core.agent.tools.note_tools import note_tool_definitions
from app.core.agent.tools.sport_planning import WeeklyPlanningTool, weekly_planning_tool_definitions
from app.core.agent.tools.sport_registry import sport_tool_definitions
from app.core.agent.tools.sport_tools import SportTools
from app.core.agent.tools.escalation_tools import escalation_tool_definitions
from app.core.agent.tools.undo_tools import undo_tool_definitions
from app.core.agent.undo import UndoJournal, UndoService, last_budget_entry
from app.core.database import get_database_manager
from app.core.dependencies import (
    get_budget_connector,
    get_budget_connector_error,
    get_calendar_connector,
    get_calendar_connector_error,
    get_task_events_connector,
    get_task_events_connector_error,
    get_tasks_connector,
    get_tasks_connector_error,
)
from app.core.expert.budget import budget_exhausted_reason
from app.core.expert.cascade import CascadeService
from app.core.expert.expert_service import ExpertService
from app.core.expert.llm import ClaudeExpertLLM, ExpertLLM
from app.core.llm.gemini_client import get_gemini_client
from app.core.sport_coach_service import SportCoachService

logger = logging.getLogger(__name__)

# Outils laissés à l'expert Claude : les suites utiles d'un conseil. Les déclarations d'outils pèsent ~78 % des tokens
# d'entrée (payants) ; sport, repas et budget restent à Gemini (décisions utilisateur du 23/11/2026).
EXPERT_TOOL_NAMES = frozenset({"add_task", "get_tasks", "get_agenda", "add_shopping_items", "save_note"})

_agent_llm: Optional[AgentLLM] = None
_expert_llm: Optional[ExpertLLM] = None


def get_agent_llm() -> AgentLLM:
    return _agent_llm or GeminiAgentLLM(get_gemini_client())


def set_agent_llm(llm: Optional[AgentLLM]) -> None:
    """Injection d'un LLM (ex. scripté) pour les tests."""
    global _agent_llm
    _agent_llm = llm


def get_expert_llm() -> Optional[ExpertLLM]:
    """Expert Claude (niveau 2) : seulement si une clé Anthropic est configurée (API payante)."""
    if _expert_llm is not None:
        return _expert_llm
    return ClaudeExpertLLM() if settings.anthropic_api_key else None


def set_expert_llm(llm: Optional[ExpertLLM]) -> None:
    """Injection d'un expert (ex. scripté) pour les tests."""
    global _expert_llm
    _expert_llm = llm


def _sport_tools(sport_connector: Any) -> SportTools:
    if not isinstance(sport_connector, SqlSportConnector):
        raise AgentUnavailableError(
            f"L'agent nécessite le carnet sport SQLite (connecteur actuel : {type(sport_connector).__name__})."
        )
    return SportTools(sport_connector)


def build_undo_service(sport_connector: Any, meals_connector: Any = None) -> UndoService:
    db = get_database_manager()
    return UndoService(
        sport_tools=_sport_tools(sport_connector), db=db, journal=UndoJournal(db), meals_tools=MealsTools(meals_connector),
        tasks_tools=_tasks_tools(), budget_tools=_budget_tools(),
    )


def _budget_tools(session_id: str = "") -> BudgetTools:
    """`session_id` : conversation dont la question « lequel ? » peut apprendre un nom de catégorie."""
    return BudgetTools(
        get_budget_connector(), unavailable_reason=get_budget_connector_error(), aliases=get_database_manager(),
        session_id=session_id, pending=get_pending_category_questions(),
    )


def _tasks_tools() -> TasksTools:
    return TasksTools(
        get_tasks_connector(), unavailable_reason=get_tasks_connector_error(),
        events=get_task_events_connector(), events_unavailable_reason=get_task_events_connector_error(),
    )


def build_cascade_service(
    sport_connector: Any, session_id: str, legacy_action_pending: bool, meals_tools: MealsTools,
    history: Sequence[ConversationTurn] = (),
) -> CascadeService:
    """Agent Gemini (niveau 1) + expert Claude (niveau 2) s'il est configuré, avec les mêmes outils métier.

    `legacy_action_pending` : la dernière action de la session vient du flux regex (ex. ajout aux courses).

    `meals_tools` sans connecteur (classeur non configuré) : les outils repas & courses répondent par une erreur explicite.
    """
    sport_tools = _sport_tools(sport_connector)
    db = get_database_manager()
    weekly_tool = WeeklyPlanningTool(sport_tools, SportCoachService(connector=sport_connector))
    tasks_tools = _tasks_tools()
    budget_tools = _budget_tools(session_id)
    journal = UndoJournal(db)
    undo_service = UndoService(
        sport_tools=sport_tools, db=db, journal=journal, meals_tools=meals_tools, tasks_tools=tasks_tools,
        budget_tools=budget_tools,
    )
    calendar_tools = CalendarTools(get_calendar_connector(), unavailable_reason=get_calendar_connector_error())
    domain_tools = (
        sport_tool_definitions(sport_tools)
        + weekly_planning_tool_definitions(weekly_tool)
        + meals_tool_definitions(meals_tools)
        + calendar_tool_definitions(calendar_tools)
        + tasks_tool_definitions(tasks_tools)
        + budget_tool_definitions(budget_tools, last_entry=lambda: last_budget_entry(journal.last(session_id)))
        + note_tool_definitions(db, history)
        + undo_tool_definitions(undo_service, session_id, legacy_action_pending)
    )
    expert_llm = get_expert_llm()
    expert_disabled = budget_exhausted_reason(db) if expert_llm else None
    if expert_disabled:
        logger.warning(f"Expert Claude non proposé : {expert_disabled}.")
        expert_llm = None
    agent_tools = domain_tools + (escalation_tool_definitions() if expert_llm else [])
    agent = AgentService(llm=get_agent_llm(), registry=ToolRegistry(agent_tools), sport_tools=sport_tools)
    expert_tools = [tool for tool in domain_tools if tool.name in EXPERT_TOOL_NAMES]
    expert = ExpertService(llm=expert_llm, registry=ToolRegistry(expert_tools)) if expert_llm else None
    return CascadeService(agent=agent, expert=expert, expert_disabled=expert_disabled)
