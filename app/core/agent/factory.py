"""Assemblage de l'agent pour une requête : outils sport (SQLite), planning hebdo, repas & courses, notes et LLM Gemini."""
from typing import Any, Optional, Sequence

from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.agent_service import AgentService, ConversationTurn
from app.core.agent.errors import AgentUnavailableError
from app.core.agent.llm import AgentLLM, GeminiAgentLLM
from app.core.agent.tool_registry import ToolRegistry
from app.core.agent.tools.meals_registry import meals_tool_definitions
from app.core.agent.tools.meals_tools import MealsTools
from app.core.agent.tools.note_tools import note_tool_definitions
from app.core.agent.tools.sport_planning import WeeklyPlanningTool, weekly_planning_tool_definitions
from app.core.agent.tools.sport_registry import sport_tool_definitions
from app.core.agent.tools.sport_tools import SportTools
from app.core.agent.tools.undo_tools import undo_tool_definitions
from app.core.agent.undo import UndoJournal, UndoService
from app.core.database import get_database_manager
from app.core.llm.gemini_client import get_gemini_client
from app.core.sport_coach_service import SportCoachService

_agent_llm: Optional[AgentLLM] = None


def get_agent_llm() -> AgentLLM:
    return _agent_llm or GeminiAgentLLM(get_gemini_client())


def set_agent_llm(llm: Optional[AgentLLM]) -> None:
    """Injection d'un LLM (ex. scripté) pour les tests."""
    global _agent_llm
    _agent_llm = llm


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
    )


def build_agent_service(
    sport_connector: Any, session_id: str, legacy_action_pending: bool, meals_tools: MealsTools,
    history: Sequence[ConversationTurn] = (),
) -> AgentService:
    """`legacy_action_pending` : la dernière action de la session vient du flux regex (ex. ajout aux courses).

    `meals_tools` sans connecteur (classeur non configuré) : les outils repas & courses répondent par une erreur explicite.
    """
    sport_tools = _sport_tools(sport_connector)
    db = get_database_manager()
    weekly_tool = WeeklyPlanningTool(sport_tools, SportCoachService(connector=sport_connector))
    undo_service = UndoService(sport_tools=sport_tools, db=db, journal=UndoJournal(db), meals_tools=meals_tools)
    registry = ToolRegistry(
        sport_tool_definitions(sport_tools)
        + weekly_planning_tool_definitions(weekly_tool)
        + meals_tool_definitions(meals_tools)
        + note_tool_definitions(db, history)
        + undo_tool_definitions(undo_service, session_id, legacy_action_pending)
    )
    return AgentService(llm=get_agent_llm(), registry=registry, sport_tools=sport_tools)
