"""Outils Tâches de l'agent : lecture, ajout et complétion dans Google Tasks via `TasksConnector`, et leur annulation.

Une tâche avec heure a aussi un événement Google Agenda de 30 min (`TaskEventsConnector`), Google Tasks ne gardant
que le jour : créé avec la tâche, supprimé quand on la coche s'il est à venir, recréé à l'annulation ou à la réouverture.
"""
from datetime import date, datetime
from datetime import time as dt_time
from typing import Callable, Dict, List, Optional, Protocol, TypeVar

from app.connectors.calendar.calendar_connector import CalendarError
from app.connectors.calendar.task_events import TaskEvent, task_start
from app.connectors.tasks.models import TaskItem
from app.connectors.tasks.tasks_connector import DEFAULT_LIST_NAME, TasksError
from app.core.agent.tools.sport_models import WEEKDAYS_FR
from app.core.agent.tools.tasks_models import (
    AddTaskArgs,
    CompleteTaskArgs,
    GetTasksArgs,
    RemovedTaskEvent,
    TaskAddedUndo,
    TaskCompletedUndo,
    TaskMutation,
    TasksView,
    TaskUndo,
    TaskView,
)
from app.core.agent.tools.tool_error import ToolError
from app.core.clock import paris_now, paris_today

T = TypeVar("T")


class TasksStore(Protocol):
    def list_open_tasks(self) -> List[TaskItem]: ...
    def get_task(self, task_id: str) -> TaskItem: ...
    def add_task(self, titre: str, echeance: Optional[date]) -> TaskItem: ...
    def set_completed(self, task_id: str, completed: bool) -> TaskItem: ...
    def delete_task(self, task_id: str) -> None: ...


class TaskEventsStore(Protocol):
    def list_task_events(self) -> Dict[str, TaskEvent]: ...
    def create_event(self, task_id: str, titre: str, debut: datetime, rappel_minutes_avant: Optional[int]) -> TaskEvent: ...
    def delete_event(self, event_id: str) -> None: ...


class TasksToolError(ToolError):
    """Erreur Google Tasks renvoyée telle quelle au modèle."""


class TasksTools:
    def __init__(
        self, connector: Optional[TasksStore], unavailable_reason: str = "",
        today: Callable[[], date] = paris_today, events: Optional[TaskEventsStore] = None,
        events_unavailable_reason: str = "", now: Callable[[], datetime] = paris_now,
    ) -> None:
        """`unavailable_reason` : cause de l'absence de connecteur (réglage OAuth manquant…), dite à l'utilisateur.

        `events` absent : les tâches restent utilisables, seules les heures (événements Agenda) sont refusées.
        """
        self._connector = connector
        self._unavailable_reason = unavailable_reason
        self._today = today
        self._events = events
        self._events_unavailable_reason = events_unavailable_reason
        self._now = now

    @property
    def events(self) -> TaskEventsStore:
        if self._events is None:
            raise TasksToolError(
                f"Google Agenda est indisponible pour l'heure des tâches : {self._events_unavailable_reason or 'non configuré'}."
            )
        return self._events

    @property
    def connector(self) -> TasksStore:
        if self._connector is None:
            raise TasksToolError(f"Google Tasks est indisponible : {self._unavailable_reason or 'non configuré'}.")
        return self._connector

    def get_tasks(self, _: GetTasksArgs) -> TasksView:
        tasks = self._call(self.connector.list_open_tasks)
        events = self._linked_events()
        today = self._today()
        return TasksView(
            liste=DEFAULT_LIST_NAME,
            nombre=len(tasks),
            taches=[_to_view(task, today, events.get(task.id)) for task in tasks],
        )

    def add_task(self, args: AddTaskArgs) -> TaskMutation:
        events = self.events if args.heure else None  # refus avant toute écriture si l'Agenda manque
        task = self._call(lambda: self.connector.add_task(args.titre, args.echeance))
        event = None
        if events is not None and args.echeance and args.heure:
            try:
                event = events.create_event(
                    task.id, task.titre, task_start(args.echeance, args.heure), args.rappel_minutes_avant,
                )
            except CalendarError as exc:
                self._call(lambda: self.connector.delete_task(task.id))  # pas de tâche sans son heure
                raise TasksToolError(f"Tâche « {task.titre} » non ajoutée : événement Agenda impossible ({exc}).") from exc
        return TaskMutation(
            action="ajoutee", tache=_to_view(task, self._today(), event),
            undos=[TaskAddedUndo(task_id=task.id, titre=task.titre, event_id=event.event_id if event else None)],
        )

    def complete_task(self, args: CompleteTaskArgs) -> TaskMutation:
        event = self._linked_events().get(args.task_id)
        task = self._call(lambda: self.connector.set_completed(args.task_id, True))
        removed = None
        if event is not None and event.debut > self._now():
            self._calendar(lambda: self.events.delete_event(event.event_id))  # pas de rappel pour une tâche faite
            removed = RemovedTaskEvent(debut=event.debut, rappel_minutes_avant=event.rappel_minutes_avant)
        return TaskMutation(
            action="terminee", tache=_to_view(task, self._today(), event),
            undos=[TaskCompletedUndo(task_id=task.id, titre=task.titre, evenement=removed)],
        )

    def reopen_task(
        self, task_id: str, heure: Optional[dt_time] = None, rappel_minutes_avant: Optional[int] = None,
    ) -> TaskView:
        """Rouvre une tâche cochée (« Annuler » de la feuille Tâches) ; `heure` : recrée son événement s'il est à venir."""
        task = self._call(lambda: self.connector.set_completed(task_id, False))
        event = None
        if heure is not None and task.echeance is not None:
            event = self._restore_event(task, task_start(task.echeance, heure), rappel_minutes_avant)
        return _to_view(task, self._today(), event)

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
            if undo.event_id:
                self._calendar(lambda: self.events.delete_event(undo.event_id))
            self._call(lambda: self.connector.delete_task(undo.task_id))
            return f"tâche « {undo.titre} » supprimée"
        task = self._call(lambda: self.connector.set_completed(undo.task_id, False))
        if undo.evenement is not None:
            self._restore_event(task, undo.evenement.debut, undo.evenement.rappel_minutes_avant)
        return f"tâche « {undo.titre} » rouverte"

    def _restore_event(self, task: TaskItem, debut: datetime, rappel: Optional[int]) -> Optional[TaskEvent]:
        """Recrée l'événement d'une tâche rouverte s'il est à venir et n'existe plus (jamais de doublon)."""
        existing = self._linked_events().get(task.id)
        if existing is not None:
            return existing
        if debut <= self._now():
            return None
        return self._calendar(lambda: self.events.create_event(task.id, task.titre, debut, rappel))

    def _linked_events(self) -> Dict[str, TaskEvent]:
        if self._events is None:
            return {}
        return self._calendar(self._events.list_task_events)

    def _call(self, operation: Callable[[], T]) -> T:
        try:
            return operation()
        except TasksError as exc:
            raise TasksToolError(str(exc)) from exc

    @staticmethod
    def _calendar(operation: Callable[[], T]) -> T:
        try:
            return operation()
        except CalendarError as exc:
            raise TasksToolError(str(exc)) from exc


def _to_view(task: TaskItem, today: date, event: Optional[TaskEvent] = None) -> TaskView:
    due = task.echeance
    on_due_day = event is not None and due is not None and event.debut.date() == due
    return TaskView(
        id=task.id,
        titre=task.titre,
        echeance=due,
        jour=WEEKDAYS_FR[due.weekday()] if due else None,
        en_retard=bool(due and due < today),
        notes=task.notes,
        parent=task.parent,
        heure=event.debut.strftime("%H:%M") if on_due_day and event else None,
        rappel_minutes_avant=event.rappel_minutes_avant if on_due_day and event else None,
    )
