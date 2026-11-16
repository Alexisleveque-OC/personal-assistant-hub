"""Router FastAPI de l'onglet « Tâches » de la PWA : lecture, ajout, cochage et réouverture dans Google Tasks.

Passe par `TasksTools`, comme l'agent vocal : même validation, mêmes erreurs explicites, même cache (invalidé à chaque écriture).
"""
from datetime import time as dt_time
from typing import Callable, Optional, TypeVar

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field, model_validator

from app.core.agent.tools.sport_models import StrictArgs
from app.core.agent.tools.tasks_models import AddTaskArgs, CompleteTaskArgs, GetTasksArgs, TasksView, TaskView
from app.core.agent.tools.tasks_tools import TasksTools, TasksToolError
from app.core.clock import paris_now, paris_today
from app.core.dependencies import (
    get_task_events_connector,
    get_task_events_connector_error,
    get_tasks_connector,
    get_tasks_connector_error,
)
from app.core.security import verify_api_key

T = TypeVar("T")

router = APIRouter(
    prefix="/api/v1/tasks",
    tags=["Tasks"],
    dependencies=[Depends(verify_api_key)],
)


class TaskCompletionPayload(StrictArgs):
    terminee: bool
    # Réouverture (« Annuler ») d'une tâche avec heure : de quoi recréer son événement Agenda supprimé à la coche.
    heure: Optional[dt_time] = None
    rappel_minutes_avant: Optional[int] = Field(None, ge=1, le=40320)

    @model_validator(mode="after")
    def _hour_only_to_reopen(self) -> "TaskCompletionPayload":
        if self.terminee and (self.heure is not None or self.rappel_minutes_avant is not None):
            raise ValueError("« heure » et « rappel_minutes_avant » ne servent qu'à rouvrir une tâche (terminee: false).")
        return self


@router.get("", response_model=TasksView)
def list_tasks() -> TasksView:
    return _run(lambda tools: tools.get_tasks(GetTasksArgs()))


@router.post("", response_model=TaskView, status_code=status.HTTP_201_CREATED)
def add_task(payload: AddTaskArgs) -> TaskView:
    return _run(lambda tools: tools.add_task(payload).tache)


@router.patch("/{task_id}", response_model=TaskView)
def set_task_completion(task_id: str, payload: TaskCompletionPayload) -> TaskView:
    if payload.terminee:
        return _run(lambda tools: tools.complete_task(CompleteTaskArgs(task_id=task_id)).tache)
    return _run(lambda tools: tools.reopen_task(task_id, payload.heure, payload.rappel_minutes_avant))


def _run(operation: Callable[[TasksTools], T]) -> T:
    """503 si Google Tasks n'est pas configuré (cause exacte), 502 si Google refuse ou échoue (message de l'API)."""
    connector = get_tasks_connector()
    if connector is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Google Tasks est indisponible : {get_tasks_connector_error() or 'non configuré'}.",
        )
    try:
        return operation(TasksTools(
            connector, today=paris_today, events=get_task_events_connector(),
            events_unavailable_reason=get_task_events_connector_error(), now=paris_now,
        ))
    except TasksToolError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
