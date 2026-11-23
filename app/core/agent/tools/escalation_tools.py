"""Outil d'escalade (Phase 6.10) : l'agent Gemini passe la main à l'expert Claude.

Exposé à Gemini seulement quand l'expert est configuré. La boucle agent s'arrête dès cet appel : la réponse
est rédigée par l'expert, sans second appel Gemini.
"""
from typing import List

from pydantic import BaseModel, Field

from app.core.agent.tool_registry import AgentTool

ESCALATION_TOOL_NAME = "demander_expert"


class EscalateArgs(BaseModel):
    question: str = Field(
        description="La demande de l'utilisateur, reformulée avec le contexte utile des échanges précédents.",
    )


class EscalationRequest(BaseModel):
    question: str
    transmis_a_l_expert: bool = True


def escalation_tool_definitions() -> List[AgentTool]:
    return [AgentTool(
        name=ESCALATION_TOOL_NAME,
        description=(
            "Passe la main à l'expert, un modèle plus puissant, quand la demande sort de tes outils (question générale, "
            "conseil, explication, bricolage, santé, achat, cuisine hors carnet…) ou demande un raisonnement en "
            "plusieurs étapes. Ne l'utilise pas pour une action ou une lecture simple sur les courses, repas, sport, "
            "tâches, agenda ou notes : tu sais les traiter. Après cet appel, n'écris rien : l'expert répond."
        ),
        args_model=EscalateArgs,
        handler=lambda args: EscalationRequest(question=args.question),
    )]
