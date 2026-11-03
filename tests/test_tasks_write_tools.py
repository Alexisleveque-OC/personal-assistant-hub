"""Outils agent `add_task` / `complete_task` (Phase 8, étape 4) : écriture dans « Mes tâches » et annulation."""
from datetime import date

import pytest

from app.connectors.tasks.models import TaskItem
from app.core.agent.prompt import build_system_prompt
from app.core.agent.tool_registry import ToolRegistry
from app.core.agent.tools.tasks_models import AddTaskArgs, CompleteTaskArgs, TaskAddedUndo, TaskCompletedUndo
from app.core.agent.tools.tasks_registry import tasks_tool_definitions
from app.core.agent.tools.tasks_tools import TasksTools
from app.core.agent.tools.tool_error import ToolError
from tests.tasks_fakes import FakeWritableTasks

TODAY = date(2026, 11, 3)


ORL = TaskItem(id="t1", titre="Prendre rendez-vous ORL")


def tools(fake: FakeWritableTasks) -> TasksTools:
    return TasksTools(fake, today=lambda: TODAY)


def test_add_task_creates_it_with_its_due_date_and_records_the_undo():
    fake = FakeWritableTasks()
    result = tools(fake).add_task(AddTaskArgs(titre=" Envoyer les documents ", echeance=date(2026, 11, 6)))
    assert result.action == "ajoutee"
    assert (result.tache.titre, result.tache.echeance, result.tache.jour) == ("Envoyer les documents", date(2026, 11, 6), "vendredi")
    assert result.undos == [TaskAddedUndo(task_id="new1", titre="Envoyer les documents")]
    assert [t.titre for t in fake.list_open_tasks()] == ["Envoyer les documents"]


def test_blank_title_is_refused_by_the_contract():
    with pytest.raises(ValueError):
        AddTaskArgs(titre="   ")


def test_complete_task_checks_it_and_records_the_undo():
    fake = FakeWritableTasks([ORL])
    result = tools(fake).complete_task(CompleteTaskArgs(task_id="t1"))
    assert (result.action, result.tache.titre) == ("terminee", "Prendre rendez-vous ORL")
    assert result.undos == [TaskCompletedUndo(task_id="t1", titre="Prendre rendez-vous ORL")]
    assert fake.list_open_tasks() == []


def test_unknown_task_id_is_reported_to_the_model():
    with pytest.raises(ToolError, match="404.*t9"):
        tools(FakeWritableTasks()).complete_task(CompleteTaskArgs(task_id="t9"))


def test_undo_of_an_added_task_deletes_it():
    fake = FakeWritableTasks()
    t = tools(fake)
    undo = t.add_task(AddTaskArgs(titre="Appeler la banque")).undos[0]
    t.check_undo(undo)
    assert t.apply_undo(undo) == "tâche « Appeler la banque » supprimée"
    assert fake.tasks == {}


def test_undo_of_a_completed_task_reopens_it():
    fake = FakeWritableTasks([ORL])
    t = tools(fake)
    undo = t.complete_task(CompleteTaskArgs(task_id="t1")).undos[0]
    t.check_undo(undo)
    assert t.apply_undo(undo) == "tâche « Prendre rendez-vous ORL » rouverte"
    assert [x.id for x in fake.list_open_tasks()] == ["t1"]


def test_undo_is_refused_when_the_task_changed_since():
    fake = FakeWritableTasks([ORL])
    t = tools(fake)
    added = t.add_task(AddTaskArgs(titre="Appeler")).undos[0]
    completed = t.complete_task(CompleteTaskArgs(task_id="t1")).undos[0]
    fake.delete_task(added.task_id)
    fake.set_completed("t1", False)
    with pytest.raises(ToolError, match="Appeler.*n'existe plus"):
        t.check_undo(added)
    with pytest.raises(ToolError, match="ORL.*n'est plus cochée"):
        t.check_undo(completed)


def test_undo_targets_identify_the_task():
    assert TasksTools.undo_targets(TaskAddedUndo(task_id="a", titre="A")) == [("task", "a")]


@pytest.mark.asyncio
async def test_registry_exposes_the_write_tools_and_keeps_undos_server_side():
    registry = ToolRegistry(tasks_tool_definitions(tools(FakeWritableTasks())))
    declarations = {d["name"]: d for d in registry.declarations()}
    assert set(declarations["add_task"]["parameters"]["properties"]) == {"titre", "echeance"}
    assert set(declarations["complete_task"]["parameters"]["properties"]) == {"task_id"}

    execution = await registry.execute("add_task", {"titre": "Appeler", "echeance": "2026-11-04"})
    assert execution.error is None
    assert execution.response["tache"]["titre"] == "Appeler"
    assert "undos" not in execution.response
    assert execution.undos == [TaskAddedUndo(task_id="new1", titre="Appeler")]


def test_prompt_sends_every_dictated_task_to_google_tasks_not_to_notes():
    prompt = build_system_prompt(TODAY, [])
    assert "add_task" in prompt
    assert "complete_task" in prompt
    assert "penser à" in prompt


def test_save_note_refuses_the_task_category_and_points_to_add_task():
    from app.core.agent.tools.note_tools import SaveNoteArgs
    with pytest.raises(ValueError, match="add_task"):
        SaveNoteArgs(content="Envoyer les documents", category="task")
    assert SaveNoteArgs(content="Idée d'appli", category="dev_idea").category.value == "dev_idea"
