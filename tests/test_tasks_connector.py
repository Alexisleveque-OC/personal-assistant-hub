"""Connecteur Google Tasks (Phase 8, étape 3) : liste par défaut, tâches non terminées, échéances, cache 3 min."""
from datetime import date

import pytest
from google.auth.exceptions import RefreshError

from app.connectors.tasks.tasks_connector import TasksAuthError, TasksConnector, TasksError
from tests.test_calendar_connector import FakeResponse, FakeSession

DEFAULT_TASKS_URL = "https://tasks.googleapis.com/tasks/v1/lists/@default/tasks"


def task(title: str, task_id: str = "", due: str = "", **extra) -> dict:
    item = {"id": task_id or title.lower(), "title": title, "status": "needsAction", **extra}
    if due:
        item["due"] = due
    return item


def make_connector(*items: dict, **kwargs) -> tuple[TasksConnector, FakeSession]:
    session = FakeSession({DEFAULT_TASKS_URL: FakeResponse({"items": list(items)})})
    return TasksConnector(session, **kwargs), session


def test_reads_the_open_tasks_of_the_default_list():
    connector, session = make_connector(task("Appeler la banque"))
    connector.list_open_tasks()
    assert session.calls[0]["url"] == DEFAULT_TASKS_URL
    params = session.calls[0]["params"]
    assert params["showCompleted"] == "false"
    assert params["showHidden"] == "false"


def test_maps_title_notes_and_due_date():
    connector, _ = make_connector(
        task("Payer la cantine", "t1", due="2026-11-05T00:00:00.000Z", notes="Avant vendredi"),
        task("Ranger le garage", "t2"),
    )
    paid, garage = connector.list_open_tasks()
    assert (paid.id, paid.titre, paid.notes, paid.echeance) == ("t1", "Payer la cantine", "Avant vendredi", date(2026, 11, 5))
    assert (garage.id, garage.titre, garage.notes, garage.echeance) == ("t2", "Ranger le garage", None, None)


def test_tasks_with_a_due_date_come_first_by_date_then_the_others_in_list_order():
    connector, _ = make_connector(
        task("Sans date A"),
        task("Plus tard", due="2026-11-20T00:00:00.000Z"),
        task("Sans date B"),
        task("Bientôt", due="2026-11-04T00:00:00.000Z"),
    )
    assert [t.titre for t in connector.list_open_tasks()] == ["Bientôt", "Plus tard", "Sans date A", "Sans date B"]


def test_completed_and_untitled_tasks_are_skipped():
    connector, _ = make_connector(
        task("Faite", status="completed"),
        task("   "),
        task("À faire"),
    )
    assert [t.titre for t in connector.list_open_tasks()] == ["À faire"]


def test_follows_pagination():
    session = FakeSession({DEFAULT_TASKS_URL: [
        FakeResponse({"items": [task("A")], "nextPageToken": "p2"}),
        FakeResponse({"items": [task("B")]}),
    ]})
    assert [t.titre for t in TasksConnector(session).list_open_tasks()] == ["A", "B"]
    assert session.calls[-1]["params"]["pageToken"] == "p2"


def test_empty_list_has_no_items_key():
    session = FakeSession({DEFAULT_TASKS_URL: FakeResponse({})})
    assert TasksConnector(session).list_open_tasks() == []


def test_served_from_cache_until_ttl_expires_or_invalidation():
    clock = [1000.0]
    connector, session = make_connector(task("A"), ttl_seconds=180, monotonic=lambda: clock[0])
    connector.list_open_tasks()
    clock[0] += 179
    connector.list_open_tasks()
    assert len(session.calls) == 1

    clock[0] += 2
    connector.list_open_tasks()
    assert len(session.calls) == 2

    connector.invalidate_cache()
    connector.list_open_tasks()
    assert len(session.calls) == 3


def test_http_error_gives_the_status_and_the_list():
    session = FakeSession({DEFAULT_TASKS_URL: FakeResponse({"error": {"message": "Forbidden"}}, status_code=403)})
    with pytest.raises(TasksError, match="403.*Mes tâches"):
        TasksConnector(session).list_open_tasks()


class RevokedSession:
    def get(self, url, params=None):
        raise RefreshError("invalid_grant: Token has been expired or revoked.")


def test_revoked_token_tells_how_to_renew_it():
    with pytest.raises(TasksAuthError) as exc:
        TasksConnector(RevokedSession()).list_open_tasks()
    message = str(exc.value)
    assert "scripts/google_oauth_login.py" in message
    assert "GOOGLE_OAUTH_REFRESH_TOKEN" in message
    assert isinstance(exc.value, TasksError)
