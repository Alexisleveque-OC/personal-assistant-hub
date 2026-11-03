"""Contrats Pydantic des outils Tâches de l'agent : arguments stricts, vues renvoyées au modèle et annulations."""
from datetime import date as dt_date
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

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


class AddTaskArgs(StrictArgs):
    titre: str = Field(description="Intitulé court de la tâche, en français, sans « rappelle-moi de ».")
    echeance: Optional[dt_date] = Field(None, description="Jour d'échéance, seulement s'il est dit par l'utilisateur.")

    @field_validator("titre")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Le titre de la tâche est vide.")
        return value.strip()


class CompleteTaskArgs(StrictArgs):
    task_id: str = Field(description="Identifiant de la tâche lu avec get_tasks (jamais deviné).")


class TaskAddedUndo(BaseModel):
    kind: Literal["task_added"] = "task_added"
    task_id: str
    titre: str


class TaskCompletedUndo(BaseModel):
    kind: Literal["task_completed"] = "task_completed"
    task_id: str
    titre: str


TaskUndo = Union[TaskAddedUndo, TaskCompletedUndo]


class TaskMutation(BaseModel):
    action: Literal["ajoutee", "terminee"]
    tache: TaskView
    undos: List[TaskUndo]
