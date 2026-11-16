"""Doublure en mémoire de `TasksConnector`, partagée par les tests des outils agent, de l'API et de bout en bout."""
from datetime import date
from typing import Dict, List, Optional

from app.connectors.tasks.models import TaskItem
from app.connectors.tasks.tasks_connector import TasksError


class FakeWritableTasks:
    """Doublure en mémoire de `TasksConnector` (lecture et écriture)."""

    def __init__(self, tasks: Optional[List[TaskItem]] = None) -> None:
        self.tasks: Dict[str, TaskItem] = {t.id: t for t in tasks or []}
        self.next_id = 1

    def list_open_tasks(self) -> List[TaskItem]:
        return [t for t in self.tasks.values() if not t.terminee]

    def get_task(self, task_id: str) -> TaskItem:
        if task_id not in self.tasks:
            raise TasksError(f"API Google Tasks : HTTP 404 en lisant la tâche {task_id}")
        return self.tasks[task_id]

    def add_task(self, titre: str, echeance: Optional[date]) -> TaskItem:
        task = TaskItem(id=f"new{self.next_id}", titre=titre, echeance=echeance)
        self.next_id += 1
        self.tasks[task.id] = task
        return task

    def set_completed(self, task_id: str, completed: bool) -> TaskItem:
        task = self.get_task(task_id).model_copy(update={"terminee": completed})
        self.tasks[task_id] = task
        return task

    def delete_task(self, task_id: str) -> None:
        self.get_task(task_id)
        del self.tasks[task_id]


class FakeTaskEvents:
    """Doublure en mémoire de `TaskEventsConnector` (événements Agenda des tâches avec heure)."""

    def __init__(self, fail_create: str = "") -> None:
        from app.connectors.calendar.task_events import TaskEvent
        self._event_cls = TaskEvent
        self.events = {}
        self.next_id = 1
        self.fail_create = fail_create

    def list_task_events(self):
        return dict(self.events)

    def create_event(self, task_id, titre, debut, rappel_minutes_avant):
        from app.connectors.calendar.calendar_connector import CalendarError
        if self.fail_create:
            raise CalendarError(self.fail_create)
        event = self._event_cls(
            task_id=task_id, event_id=f"ev{self.next_id}", debut=debut, rappel_minutes_avant=rappel_minutes_avant,
        )
        self.next_id += 1
        self.titles = getattr(self, "titles", {})
        self.titles[event.event_id] = titre
        self.events[task_id] = event
        return event

    def delete_event(self, event_id):
        self.events = {k: v for k, v in self.events.items() if v.event_id != event_id}
