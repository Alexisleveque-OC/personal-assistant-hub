"""Contrats Pydantic des outils Tâches de l'agent : arguments stricts, vues renvoyées au modèle et annulations."""
from datetime import date as dt_date
from datetime import datetime
from datetime import time as dt_time
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

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
    parent: Optional[str] = Field(None, description="Id de la tâche parente (sous-tâche).")
    heure: Optional[str] = Field(None, description="Heure de l'événement Agenda lié (HH:MM), le jour de l'échéance.")
    rappel_minutes_avant: Optional[int] = Field(None, description="Rappel ajouté en plus de ceux de l'agenda.")


class TasksView(BaseModel):
    liste: str
    nombre: int
    taches: List[TaskView]


class AddTaskArgs(StrictArgs):
    titre: str = Field(description="Intitulé court de la tâche, en français, sans « rappelle-moi de ».")
    echeance: Optional[dt_date] = Field(None, description="Jour d'échéance, seulement s'il est dit par l'utilisateur.")
    heure: Optional[dt_time] = Field(
        None, description="Heure (HH:MM) seulement si elle est dite ; crée un événement Agenda de 30 min ce jour-là.",
    )
    rappel_minutes_avant: Optional[int] = Field(
        None, ge=1, le=40320,
        description="Rappel en plus, seulement s'il est demandé, en minutes avant l'heure (« la veille » = 1440).",
    )

    @field_validator("titre")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Le titre de la tâche est vide.")
        return value.strip()

    @model_validator(mode="after")
    def _hour_needs_day(self) -> "AddTaskArgs":
        if self.heure is not None and self.echeance is None:
            raise ValueError("Une heure de tâche demande aussi le jour (echeance) : aujourd'hui si seule l'heure est dite.")
        if self.rappel_minutes_avant is not None and self.heure is None:
            raise ValueError("Un rappel demande une heure de tâche (heure) : demander l'heure à l'utilisateur.")
        return self


class CompleteTaskArgs(StrictArgs):
    task_id: str = Field(description="Identifiant de la tâche lu avec get_tasks (jamais deviné).")


class TaskAddedUndo(BaseModel):
    kind: Literal["task_added"] = "task_added"
    task_id: str
    titre: str
    event_id: Optional[str] = None  # événement Agenda créé avec la tâche (tâche avec heure)


class RemovedTaskEvent(BaseModel):
    """Événement à venir supprimé en cochant la tâche : de quoi le recréer à l'annulation."""
    debut: datetime
    rappel_minutes_avant: Optional[int] = None


class TaskCompletedUndo(BaseModel):
    kind: Literal["task_completed"] = "task_completed"
    task_id: str
    titre: str
    evenement: Optional[RemovedTaskEvent] = None


TaskUndo = Union[TaskAddedUndo, TaskCompletedUndo]


class TaskMutation(BaseModel):
    action: Literal["ajoutee", "terminee"]
    tache: TaskView
    undos: List[TaskUndo]
