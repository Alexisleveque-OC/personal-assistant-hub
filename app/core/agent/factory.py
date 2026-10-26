"""Assemblage de l'agent pour une requête : outils sport (SQLite), planning hebdo, notes et LLM Gemini."""
from typing import Any, Optional

from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.agent_service import AgentService
from app.core.agent.errors import AgentUnavailableError
from app.core.agent.llm import AgentLLM, GeminiAgentLLM
from app.core.agent.tool_registry import ToolRegistry
from app.core.agent.tools.note_tools import note_tool_definitions
from app.core.agent.tools.sport_planning import WeeklyPlanningTool, weekly_planning_tool_definitions
from app.core.agent.tools.sport_registry import sport_tool_definitions
from app.core.agent.tools.sport_tools import SportTools
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


def build_agent_service(sport_connector: Any) -> AgentService:
    if not isinstance(sport_connector, SqlSportConnector):
        raise AgentUnavailableError(
            f"L'agent nécessite le carnet sport SQLite (connecteur actuel : {type(sport_connector).__name__})."
        )
    sport_tools = SportTools(sport_connector)
    weekly_tool = WeeklyPlanningTool(sport_tools, SportCoachService(connector=sport_connector))
    registry = ToolRegistry(
        sport_tool_definitions(sport_tools)
        + weekly_planning_tool_definitions(weekly_tool)
        + note_tool_definitions(get_database_manager())
    )
    return AgentService(llm=get_agent_llm(), registry=registry, sport_tools=sport_tools)
