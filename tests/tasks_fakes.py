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
