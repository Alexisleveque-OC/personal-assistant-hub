"""Outils Tâches de l'agent : lecture, ajout et complétion dans Google Tasks via `TasksConnector`, et leur annulation."""
from datetime import date
from typing import Callable, List, Optional, Protocol, TypeVar

from app.connectors.tasks.models import TaskItem
from app.connectors.tasks.tasks_connector import DEFAULT_LIST_NAME, TasksError
from app.core.agent.tools.sport_models import WEEKDAYS_FR
from app.core.agent.tools.tasks_models import (
    AddTaskArgs,
    CompleteTaskArgs,
    GetTasksArgs,
    TaskAddedUndo,
    TaskCompletedUndo,
    TaskMutation,
    TasksView,
    TaskUndo,
    TaskView,
)
from app.core.agent.tools.tool_error import ToolError
from app.core.clock import paris_today

T = TypeVar("T")


class TasksStore(Protocol):
    def list_open_tasks(self) -> List[TaskItem]: ...
    def get_task(self, task_id: str) -> TaskItem: ...
    def add_task(self, titre: str, echeance: Optional[date]) -> TaskItem: ...
    def set_completed(self, task_id: str, completed: bool) -> TaskItem: ...
    def delete_task(self, task_id: str) -> None: ...


class TasksToolError(ToolError):
    """Erreur Google Tasks renvoyée telle quelle au modèle."""


class TasksTools:
    def __init__(
        self, connector: Optional[TasksStore], unavailable_reason: str = "",
        today: Callable[[], date] = paris_today,
    ) -> None:
        """`unavailable_reason` : cause de l'absence de connecteur (réglage OAuth manquant…), dite à l'utilisateur."""
        self._connector = connector
        self._unavailable_reason = unavailable_reason
        self._today = today

    @property
    def connector(self) -> TasksStore:
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

    def add_task(self, args: AddTaskArgs) -> TaskMutation:
        task = self._call(lambda: self.connector.add_task(args.titre, args.echeance))
        return TaskMutation(
            action="ajoutee", tache=_to_view(task, self._today()), undos=[TaskAddedUndo(task_id=task.id, titre=task.titre)],
        )

    def complete_task(self, args: CompleteTaskArgs) -> TaskMutation:
        task = self._call(lambda: self.connector.set_completed(args.task_id, True))
        return TaskMutation(
            action="terminee", tache=_to_view(task, self._today()),
            undos=[TaskCompletedUndo(task_id=task.id, titre=task.titre)],
        )

    def reopen_task(self, task_id: str) -> TaskView:
        """Rouvre une tâche cochée (bouton « Annuler » de l'onglet Tâches de la PWA)."""
        task = self._call(lambda: self.connector.set_completed(task_id, False))
        return _to_view(task, self._today())

    @staticmethod
    def undo_targets(undo: TaskUndo) -> List[tuple]:
        return [("task", undo.task_id)]

    def check_undo(self, undo: TaskUndo) -> None:
        """Annulation refusée si la tâche a changé depuis l'action de l'assistant (supprimée, rouverte)."""
        try:
            current = self.connector.get_task(undo.task_id)
        except TasksError as exc:
            raise TasksToolError(f"Annulation impossible : la tâche « {undo.titre} » n'existe plus ({exc}).") from exc
        if isinstance(undo, TaskCompletedUndo) and not current.terminee:
            raise TasksToolError(f"Annulation impossible : la tâche « {undo.titre} » n'est plus cochée.")

    def apply_undo(self, undo: TaskUndo) -> str:
        if isinstance(undo, TaskAddedUndo):
            self._call(lambda: self.connector.delete_task(undo.task_id))
            return f"tâche « {undo.titre} » supprimée"
        self._call(lambda: self.connector.set_completed(undo.task_id, False))
        return f"tâche « {undo.titre} » rouverte"

    def _call(self, operation: Callable[[], T]) -> T:
        try:
            return operation()
        except TasksError as exc:
            raise TasksToolError(str(exc)) from exc


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
