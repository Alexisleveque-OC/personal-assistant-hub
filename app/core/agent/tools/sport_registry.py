"""Déclaration des outils sport exposés à l'agent."""
from typing import List

from app.core.agent.tool_registry import AgentTool, ToolRegistry
from app.core.agent.tools.sport_models import (
    FindSessionsArgs,
    GetSessionArgs,
    LogSessionArgs,
    PlanSessionArgs,
    UpdateSessionArgs,
)
from app.core.agent.tools.sport_tools import SportTools


def build_sport_registry(tools: SportTools) -> ToolRegistry:
    return ToolRegistry(sport_tool_definitions(tools))


def sport_tool_definitions(tools: SportTools) -> List[AgentTool]:
    return [
        AgentTool(
            name="find_sport_sessions",
            description=(
                "Cherche des séances du carnet d'entraînement, les plus récentes d'abord. "
                "Sert à identifier la séance visée (par son id) avant toute modification."
            ),
            args_model=FindSessionsArgs,
            handler=tools.find_sport_sessions,
        ),
        AgentTool(
            name="get_sport_session",
            description="Lit le détail complet d'une séance à partir de son identifiant.",
            args_model=GetSessionArgs,
            handler=lambda args: tools.get_sport_session(args.session_id),
        ),
        AgentTool(
            name="update_sport_session",
            description=(
                "Modifie une séance EXISTANTE identifiée par son id (ressenti, météo, type, date…). "
                "Ne renseigner que les champs explicitement donnés par l'utilisateur."
            ),
            args_model=UpdateSessionArgs,
            handler=tools.update_sport_session,
        ),
        AgentTool(
            name="log_sport_session",
            description=(
                "Crée une NOUVELLE séance réalisée (aujourd'hui ou dans le passé) absente du carnet. "
                "Si la séance existe déjà, utiliser update_sport_session. N'invente aucune valeur non dite."
            ),
            args_model=LogSessionArgs,
            handler=tools.log_sport_session,
        ),
        AgentTool(
            name="plan_sport_session",
            description="Planifie une NOUVELLE séance future (statut Prévu), aujourd'hui ou plus tard.",
            args_model=PlanSessionArgs,
            handler=tools.plan_sport_session,
        ),
    ]
