"""Outil Tâches de l'agent : lecture de Google Tasks via `TasksConnector`, échéances datées à Paris."""
from datetime import date
from typing import Callable, List, Optional, Protocol

from app.connectors.tasks.models import TaskItem
from app.connectors.tasks.tasks_connector import DEFAULT_LIST_NAME, TasksError
from app.core.agent.tools.sport_models import WEEKDAYS_FR
from app.core.agent.tools.tasks_models import GetTasksArgs, TasksView, TaskView
from app.core.agent.tools.tool_error import ToolError
from app.core.clock import paris_today


class TasksReader(Protocol):
    def list_open_tasks(self) -> List[TaskItem]: ...


class TasksToolError(ToolError):
    """Erreur Google Tasks renvoyée telle quelle au modèle."""


class TasksTools:
    def __init__(
        self, connector: Optional[TasksReader], unavailable_reason: str = "",
        today: Callable[[], date] = paris_today,
    ) -> None:
        """`unavailable_reason` : cause de l'absence de connecteur (réglage OAuth manquant…), dite à l'utilisateur."""
        self._connector = connector
        self._unavailable_reason = unavailable_reason
        self._today = today

    @property
    def connector(self) -> TasksReader:
        if self._connector is None:
            raise TasksToolError(f"Google Tasks est indisponible : {self._unavailable_reason or 'non configuré'}.")
        return self._connector

    def get_tasks(self, _: GetTasksArgs) -> TasksView:
        try:
            tasks = self.connector.list_open_tasks()
        except TasksError as exc:
            raise TasksToolError(str(exc)) from exc
        today = self._today()
        return TasksView(
            liste=DEFAULT_LIST_NAME,
            nombre=len(tasks),
            taches=[_to_view(task, today) for task in tasks],
        )


def _to_view(task: TaskItem, today: date) -> TaskView:
    due = task.echeance
    return TaskView(
        id=task.id,
        titre=task.titre,
        echeance=due,
        jour=WEEKDAYS_FR[due.weekday()] if due else None,
        en_retard=bool(due and due < today),
        notes=task.notes,
    )
