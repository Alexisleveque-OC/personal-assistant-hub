"""Déclaration des outils Agenda exposés à l'agent."""
from typing import List

from app.core.agent.tool_registry import AgentTool
from app.core.agent.tools.calendar_models import GetAgendaArgs
from app.core.agent.tools.calendar_tools import CalendarTools


def calendar_tool_definitions(tools: CalendarTools) -> List[AgentTool]:
    return [
        AgentTool(
            name="get_agenda",
            description=(
                "Lit l'Agenda Google de l'utilisateur (tous ses agendas affichés) jour par jour, sur 14 jours maximum : "
                "événements sur la journée entière, rendez-vous avec heures, lieu et agenda d'origine. "
                "Un jour sans événement est renvoyé avec une liste vide."
            ),
            args_model=GetAgendaArgs,
            handler=tools.get_agenda,
        ),
    ]
