"""Contrats Pydantic de l'outil Tâches de l'agent : arguments stricts et vue renvoyée au modèle."""
from datetime import date as dt_date
from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.agent.tools.sport_models import StrictArgs


class GetTasksArgs(StrictArgs):
    """Aucun argument : tâches non terminées de la liste par défaut."""


class TaskView(BaseModel):
    id: str
    titre: str
    echeance: Optional[dt_date] = None
    jour: Optional[str] = Field(None, description="Jour de la semaine de l'échéance.")
    en_retard: bool = Field(description="Échéance dépassée (antérieure à aujourd'hui).")
    notes: Optional[str] = None


class TasksView(BaseModel):
    liste: str
    nombre: int
    taches: List[TaskView]
