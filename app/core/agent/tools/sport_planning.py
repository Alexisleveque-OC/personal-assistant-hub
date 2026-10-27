"""Outil agent de planning hebdomadaire : le coach Gemini propose, les séances sont créées sans rien écraser."""
from datetime import date as dt_date
import logging
from typing import List, Optional, Protocol

from pydantic import BaseModel, Field

from app.connectors.sheets.sport_models import SportSessionType, SportWeeklyPlanProposal
from app.core.agent.tool_registry import AgentTool
from app.core.agent.tools.sport_models import (
    FindSessionsArgs,
    PlanSessionArgs,
    SessionView,
    UndoSnapshot,
    StrictArgs,
)
from app.core.agent.tools.sport_tools import SportToolError, SportTools

logger = logging.getLogger(__name__)


class WeeklyCoach(Protocol):
    async def plan_weekly_training(
        self, query: str = "", target_week: Optional[int] = None, target_year: Optional[int] = None
    ) -> SportWeeklyPlanProposal: ...


class PlanWeekArgs(StrictArgs):
    semaine: Optional[int] = Field(None, ge=1, le=53, description="Semaine ISO visée (par défaut : semaine courante ou suivante).")
    annee: Optional[int] = Field(None, ge=2000, le=2100)
    consignes: Optional[str] = Field(None, description="Souhaits de l'utilisateur pour la semaine, en français.")


class SkippedDay(BaseModel):
    date: Optional[dt_date] = None
    type_seance: SportSessionType
    raison: str


class WeeklyPlanResult(BaseModel):
    resume: str
    created: List[SessionView]
    skipped: List[SkippedDay]
    undos: List[UndoSnapshot]


class WeeklyPlanningTool:
    def __init__(self, sport_tools: SportTools, coach: WeeklyCoach) -> None:
        self.sport_tools = sport_tools
        self.coach = coach

    async def plan_weekly_training(self, args: PlanWeekArgs) -> WeeklyPlanResult:
        try:
            proposal = await self.coach.plan_weekly_training(
                query=args.consignes or "", target_week=args.semaine, target_year=args.annee,
            )
        except Exception as exc:
            logger.error(f"Planning hebdomadaire : échec du coach ({exc})", exc_info=True)
            raise SportToolError(f"Planification hebdomadaire impossible : {exc}") from exc

        today = self.sport_tools.today()
        created: List[SessionView] = []
        skipped: List[SkippedDay] = []
        undos: List[UndoSnapshot] = []
        for seance in proposal.seances:
            day = seance.date_seance
            if day is None:
                skipped.append(SkippedDay(type_seance=seance.type_seance, raison="date non calculée par le coach"))
                continue
            if day < today:
                skipped.append(SkippedDay(date=day, type_seance=seance.type_seance, raison="jour passé"))
                continue
            busy = self.sport_tools.find_sport_sessions(FindSessionsArgs(date_from=day, date_to=day))
            if busy:
                occupied = ", ".join(f"{s.type_seance.value} {s.statut.value}" for s in busy)
                skipped.append(SkippedDay(date=day, type_seance=seance.type_seance, raison=f"jour déjà occupé ({occupied})"))
                continue
            result = self.sport_tools.plan_sport_session(PlanSessionArgs(
                date=day,
                type_seance=seance.type_seance,
                distance_km=seance.distance_km,
                duree_secondes=seance.duree_minutes * 60 if seance.duree_minutes else None,
                programme=seance.programme,
                remarques=seance.remarques_coach,
                allure_cible=seance.allure_cible,
                vitesse_cible=seance.vitesse_cible,
            ))
            created.append(result.session)
            undos.append(result.undo)

        return WeeklyPlanResult(resume=proposal.spoken_summary, created=created, skipped=skipped, undos=undos)


def weekly_planning_tool_definitions(tool: WeeklyPlanningTool) -> List[AgentTool]:
    return [AgentTool(
        name="plan_weekly_training",
        description=(
            "Génère avec le coach le planning d'entraînement de la semaine à partir de l'historique, "
            "puis crée les séances prévues. Les jours passés ou déjà occupés sont ignorés et signalés."
        ),
        args_model=PlanWeekArgs,
        handler=tool.plan_weekly_training,
    )]
