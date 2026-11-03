"""Outil agent `get_tasks` (Phase 8, étape 3) : tâches ouvertes de « Mes tâches », échéances et retards."""
from datetime import date
from typing import List, Optional

import pytest

from app.connectors.tasks.models import TaskItem
from app.connectors.tasks.tasks_connector import TasksError
from app.core.agent.prompt import build_system_prompt
from app.core.agent.tool_registry import ToolRegistry
from app.core.agent.tools.tasks_models import GetTasksArgs
from app.core.agent.tools.tasks_registry import tasks_tool_definitions
from app.core.agent.tools.tasks_tools import TasksTools
from app.core.agent.tools.tool_error import ToolError

TODAY = date(2026, 11, 3)  # mardi


class FakeTasks:
    def __init__(self, tasks: List[TaskItem], error: Optional[Exception] = None) -> None:
        self.tasks = tasks
        self.error = error
        self.calls = 0

    def list_open_tasks(self) -> List[TaskItem]:
        self.calls += 1
        if self.error:
            raise self.error
        return self.tasks


CANTINE = TaskItem(id="t1", titre="Payer la cantine", echeance=date(2026, 11, 5), notes="Avant vendredi")
IMPOTS = TaskItem(id="t2", titre="Déclarer les impôts", echeance=date(2026, 11, 1))
GARAGE = TaskItem(id="t3", titre="Ranger le garage")


def tools(tasks: List[TaskItem], **kwargs) -> TasksTools:
    return TasksTools(FakeTasks(tasks, **kwargs), today=lambda: TODAY)


def test_lists_open_tasks_with_due_day_and_overdue_flag():
    view = tools([IMPOTS, CANTINE, GARAGE]).get_tasks(GetTasksArgs())
    assert view.liste == "Mes tâches"
    assert view.nombre == 3
    assert [(t.id, t.titre, t.echeance, t.jour, t.en_retard, t.notes) for t in view.taches] == [
        ("t2", "Déclarer les impôts", date(2026, 11, 1), "dimanche", True, None),
        ("t1", "Payer la cantine", date(2026, 11, 5), "jeudi", False, "Avant vendredi"),
        ("t3", "Ranger le garage", None, None, False, None),
    ]


def test_task_due_today_is_not_overdue():
    view = tools([TaskItem(id="t", titre="Aujourd'hui", echeance=TODAY)]).get_tasks(GetTasksArgs())
    assert view.taches[0].en_retard is False


def test_empty_list():
    view = tools([]).get_tasks(GetTasksArgs())
    assert (view.nombre, view.taches) == (0, [])


def test_unconfigured_tasks_gives_the_reason():
    unavailable = TasksTools(None, unavailable_reason="Réglages OAuth Google manquants : GOOGLE_OAUTH_REFRESH_TOKEN")
    with pytest.raises(ToolError, match="Tasks.*GOOGLE_OAUTH_REFRESH_TOKEN"):
        unavailable.get_tasks(GetTasksArgs())


def test_tasks_errors_are_passed_to_the_model_as_is():
    with pytest.raises(ToolError, match="403"):
        tools([], error=TasksError("API Google Tasks : HTTP 403")).get_tasks(GetTasksArgs())


@pytest.mark.asyncio
async def test_registry_exposes_get_tasks_without_arguments():
    registry = ToolRegistry(tasks_tool_definitions(tools([CANTINE])))
    declaration = next(d for d in registry.declarations() if d["name"] == "get_tasks")
    assert "parameters" not in declaration or not declaration["parameters"].get("properties")

    execution = await registry.execute("get_tasks", {})
    assert execution.error is None
    assert execution.response["taches"][0]["titre"] == "Payer la cantine"


def test_prompt_tells_how_to_read_tasks_aloud_and_not_to_confuse_them_with_shopping():
    prompt = build_system_prompt(date(2026, 11, 3), [])
    assert "get_tasks" in prompt
    assert "courses" in prompt.split("get_tasks", 1)[1].split("\n\n", 1)[0]
