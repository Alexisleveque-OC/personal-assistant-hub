"""Tâches avec heure (étape 5 de la refonte) : événement Agenda de 30 min, rappel en plus, coche et annulation."""
from datetime import date, datetime, time

import pytest

from app.connectors.tasks.models import TaskItem
from app.core.agent.tools.tasks_models import AddTaskArgs, CompleteTaskArgs, GetTasksArgs
from app.core.agent.tools.tasks_tools import TasksTools
from app.core.agent.tools.tool_error import ToolError
from app.core.clock import APP_TIMEZONE
from tests.tasks_fakes import FakeTaskEvents, FakeWritableTasks

TODAY = date(2026, 11, 16)
NOW = datetime(2026, 11, 16, 9, 0, tzinfo=APP_TIMEZONE)


def tools(fake, events) -> TasksTools:
    return TasksTools(fake, today=lambda: TODAY, events=events, now=lambda: NOW)


def test_add_task_with_hour_creates_the_linked_event():
    fake, events = FakeWritableTasks(), FakeTaskEvents()
    result = tools(fake, events).add_task(AddTaskArgs(titre="ORL", echeance=date(2026, 11, 19), heure=time(14, 30)))
    event = events.events["new1"]
    assert event.debut == datetime(2026, 11, 19, 14, 30, tzinfo=APP_TIMEZONE)
    assert event.rappel_minutes_avant is None
    assert events.titles[event.event_id] == "ORL"
    assert (result.tache.heure, result.tache.rappel_minutes_avant) == ("14:30", None)
    assert result.undos[0].event_id == event.event_id


def test_extra_reminder_is_passed_to_the_event():
    fake, events = FakeWritableTasks(), FakeTaskEvents()
    result = tools(fake, events).add_task(AddTaskArgs(
        titre="ORL", echeance=date(2026, 11, 19), heure=time(14, 30), rappel_minutes_avant=1440,
    ))
    assert events.events["new1"].rappel_minutes_avant == 1440
    assert result.tache.rappel_minutes_avant == 1440


def test_add_task_without_hour_creates_no_event():
    fake, events = FakeWritableTasks(), FakeTaskEvents()
    tools(fake, events).add_task(AddTaskArgs(titre="Radio", echeance=date(2026, 11, 19)))
    assert events.events == {}


def test_hour_without_day_and_reminder_without_hour_are_refused():
    with pytest.raises(ValueError, match="jour"):
        AddTaskArgs(titre="ORL", heure=time(14, 30))
    with pytest.raises(ValueError, match="heure"):
        AddTaskArgs(titre="ORL", echeance=date(2026, 11, 19), rappel_minutes_avant=60)


def test_failed_event_removes_the_task_and_says_why():
    fake, events = FakeWritableTasks(), FakeTaskEvents(fail_create="HTTP 403 droit manquant")
    with pytest.raises(ToolError, match="403"):
        tools(fake, events).add_task(AddTaskArgs(titre="ORL", echeance=date(2026, 11, 19), heure=time(14, 30)))
    assert fake.tasks == {}


def test_get_tasks_shows_hour_reminder_and_parent():
    fake = FakeWritableTasks([
        TaskItem(id="p1", titre="Rendez-vous à prendre"),
        TaskItem(id="c1", titre="ORL", echeance=date(2026, 11, 19), parent="p1"),
    ])
    events = FakeTaskEvents()
    events.create_event("c1", "ORL", datetime(2026, 11, 19, 14, 30, tzinfo=APP_TIMEZONE), 1440)
    view = tools(fake, events).get_tasks(GetTasksArgs())
    parent, child = view.taches
    assert (parent.parent, parent.heure) == (None, None)
    assert (child.parent, child.heure, child.rappel_minutes_avant) == ("p1", "14:30", 1440)


def test_event_on_another_day_than_the_due_date_is_ignored():
    # Échéance déplacée dans Google Tasks : l'heure de l'ancien jour ne s'applique plus.
    fake = FakeWritableTasks([TaskItem(id="c1", titre="ORL", echeance=date(2026, 11, 20))])
    events = FakeTaskEvents()
    events.create_event("c1", "ORL", datetime(2026, 11, 19, 14, 30, tzinfo=APP_TIMEZONE), None)
    assert tools(fake, events).get_tasks(GetTasksArgs()).taches[0].heure is None


def test_completing_a_task_deletes_its_upcoming_event_and_undo_recreates_it():
    fake, events = FakeWritableTasks(), FakeTaskEvents()
    t = tools(fake, events)
    t.add_task(AddTaskArgs(titre="ORL", echeance=date(2026, 11, 19), heure=time(14, 30), rappel_minutes_avant=1440))
    undo = t.complete_task(CompleteTaskArgs(task_id="new1")).undos[0]
    assert events.events == {}
    t.check_undo(undo)
    t.apply_undo(undo)
    assert not fake.tasks["new1"].terminee
    recreated = events.events["new1"]
    assert (recreated.debut.hour, recreated.debut.minute, recreated.rappel_minutes_avant) == (14, 30, 1440)


def test_completing_a_task_keeps_a_past_event():
    fake = FakeWritableTasks([TaskItem(id="c1", titre="ORL", echeance=date(2026, 11, 16))])
    events = FakeTaskEvents()
    events.create_event("c1", "ORL", datetime(2026, 11, 16, 8, 0, tzinfo=APP_TIMEZONE), None)
    undo = tools(fake, events).complete_task(CompleteTaskArgs(task_id="c1")).undos[0]
    assert "c1" in events.events
    assert undo.evenement is None


def test_reopen_recreates_the_event_from_the_given_hour():
    fake = FakeWritableTasks([TaskItem(id="c1", titre="ORL", echeance=date(2026, 11, 19), terminee=True)])
    events = FakeTaskEvents()
    view = tools(fake, events).reopen_task("c1", heure=time(14, 30), rappel_minutes_avant=60)
    assert events.events["c1"].rappel_minutes_avant == 60
    assert view.heure == "14:30"


def test_reopen_does_not_duplicate_an_existing_event():
    fake = FakeWritableTasks([TaskItem(id="c1", titre="ORL", echeance=date(2026, 11, 16), terminee=True)])
    events = FakeTaskEvents()
    events.create_event("c1", "ORL", datetime(2026, 11, 16, 8, 0, tzinfo=APP_TIMEZONE), None)
    tools(fake, events).reopen_task("c1", heure=time(8, 0))
    assert [e.event_id for e in events.events.values()] == ["ev1"]


def test_undo_of_an_added_task_with_hour_deletes_its_event_too():
    fake, events = FakeWritableTasks(), FakeTaskEvents()
    t = tools(fake, events)
    undo = t.add_task(AddTaskArgs(titre="ORL", echeance=date(2026, 11, 19), heure=time(14, 30))).undos[0]
    t.apply_undo(undo)
    assert (fake.tasks, events.events) == ({}, {})


def test_hour_without_calendar_connector_is_refused_before_writing():
    fake = FakeWritableTasks()
    t = TasksTools(fake, today=lambda: TODAY, now=lambda: NOW, events_unavailable_reason="jeton absent")
    with pytest.raises(ToolError, match="Agenda.*jeton absent"):
        t.add_task(AddTaskArgs(titre="ORL", echeance=date(2026, 11, 19), heure=time(14, 30)))
    assert fake.tasks == {}


def test_completed_undo_with_removed_event_survives_the_journal_round_trip():
    from app.core.agent.undo import _UNDOS_ADAPTER
    fake, events = FakeWritableTasks(), FakeTaskEvents()
    t = tools(fake, events)
    t.add_task(AddTaskArgs(titre="ORL", echeance=date(2026, 11, 19), heure=time(14, 30), rappel_minutes_avant=60))
    undos = t.complete_task(CompleteTaskArgs(task_id="new1")).undos
    restored = _UNDOS_ADAPTER.validate_json(_UNDOS_ADAPTER.dump_json(undos))
    assert restored == undos
