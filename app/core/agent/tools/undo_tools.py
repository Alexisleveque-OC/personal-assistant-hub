"""Outil agent d'annulation, pour les demandes composées (« annule ça et note que… »)."""
from typing import List

from app.core.agent.tool_registry import AgentTool
from app.core.agent.tools.sport_models import StrictArgs
from app.core.agent.undo import UndoError, UndoOutcome, UndoService


class UndoLastActionArgs(StrictArgs):
    """Aucun argument : annule le dernier tour d'actions de l'assistant dans cette conversation."""


def undo_tool_definitions(service: UndoService, session_id: str, legacy_action_pending: bool) -> List[AgentTool]:
    def undo_last_action(_: UndoLastActionArgs) -> UndoOutcome:
        if legacy_action_pending:
            raise UndoError(
                "La dernière action de cette conversation (ex. ajout aux courses) ne vient pas de l'agent : "
                "demande à l'utilisateur de dire simplement « annule ça »."
            )
        return service.undo_last(session_id)

    return [AgentTool(
        name="undo_last_action",
        description=(
            "Annule exactement le dernier tour d'actions de l'assistant (séances modifiées ou créées, notes). "
            "Refuse si les données ont été modifiées depuis."
        ),
        args_model=UndoLastActionArgs,
        handler=undo_last_action,
    )]
