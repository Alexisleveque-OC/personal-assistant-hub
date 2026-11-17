"""API REST des tâches pour l'onglet « Tâches » de la PWA (Phase 8, étape 4 bis).

Réutilise `TasksTools` (même validation et mêmes erreurs explicites que l'agent) au-dessus du connecteur Google Tasks.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.connectors.tasks.models import TaskItem
from app.core.dependencies import set_tasks_connector
from app.main import app
from app.routers import tasks as tasks_router
from tests.tasks_fakes import FakeWritableTasks

client = TestClient(app)
TODAY = date(2026, 11, 3)


@pytest.fixture
def fake(monkeypatch) -> FakeWritableTasks:
    store = FakeWritableTasks([
        TaskItem(id="t1", titre="Prendre rendez-vous ORL", echeance=date(2026, 11, 2)),
        TaskItem(id="t2", titre="Rappeler le garage"),
    ])
    set_tasks_connector(store)
    monkeypatch.setattr(tasks_router, "paris_today", lambda: TODAY)
    return store


def test_lists_open_tasks_with_weekday_and_overdue_flag(fake):
    res = client.get("/api/v1/tasks")

    assert res.status_code == 200
    body = res.json()
    assert (body["liste"], body["nombre"]) == ("Mes tâches", 2)
    orl = body["taches"][0]
    assert (orl["id"], orl["titre"], orl["echeance"], orl["jour"], orl["en_retard"]) == (
        "t1", "Prendre rendez-vous ORL", "2026-11-02", "lundi", True,
    )
    assert body["taches"][1]["echeance"] is None


def test_unconfigured_tasks_answer_503_with_the_reason():
    set_tasks_connector(None, error="GOOGLE_OAUTH_REFRESH_TOKEN manquant")

    res = client.get("/api/v1/tasks")

    assert res.status_code == 503
    assert "GOOGLE_OAUTH_REFRESH_TOKEN manquant" in res.json()["detail"]


def test_adds_a_task_with_trimmed_title_and_due_date(fake):
    res = client.post("/api/v1/tasks", json={"titre": "  Envoyer les documents ", "echeance": "2026-11-06"})

    assert res.status_code == 201
    created = res.json()
    assert (created["titre"], created["echeance"], created["jour"]) == ("Envoyer les documents", "2026-11-06", "vendredi")
    assert "Envoyer les documents" in [t.titre for t in fake.list_open_tasks()]


def test_adds_a_task_without_due_date(fake):
    res = client.post("/api/v1/tasks", json={"titre": "Acheter des ampoules"})

    assert res.status_code == 201
    assert res.json()["echeance"] is None


def test_blank_title_is_refused(fake):
    res = client.post("/api/v1/tasks", json={"titre": "   "})

    assert res.status_code == 422


def test_unknown_fields_are_refused(fake):
    res = client.post("/api/v1/tasks", json={"titre": "Ok", "liste": "Autre"})

    assert res.status_code == 422


def test_completes_then_reopens_a_task(fake):
    res = client.patch("/api/v1/tasks/t2", json={"terminee": True})
    assert res.status_code == 200
    assert res.json()["id"] == "t2"
    assert [t.id for t in fake.list_open_tasks()] == ["t1"]

    res = client.patch("/api/v1/tasks/t2", json={"terminee": False})
    assert res.status_code == 200
    assert sorted(t.id for t in fake.list_open_tasks()) == ["t1", "t2"]


def test_google_error_on_unknown_task_answers_502_with_the_google_message(fake):
    res = client.patch("/api/v1/tasks/t9", json={"terminee": True})

    assert res.status_code == 502
    assert "404" in res.json()["detail"] and "t9" in res.json()["detail"]


def test_tasks_api_requires_the_api_key(fake, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "secret")

    assert client.get("/api/v1/tasks").status_code == 401
    assert client.get("/api/v1/tasks", headers={"X-API-Key": "secret"}).status_code == 200


# --- Tâches avec heure (refonte UX, étape 5) : événement Agenda lié ---------------------------------------------

from datetime import datetime  # noqa: E402

from app.core.clock import APP_TIMEZONE  # noqa: E402
from app.core.dependencies import set_task_events_connector  # noqa: E402
from tests.tasks_fakes import FakeTaskEvents  # noqa: E402

NOW = datetime(2026, 11, 3, 9, 0, tzinfo=APP_TIMEZONE)


@pytest.fixture
def events(fake, monkeypatch) -> FakeTaskEvents:
    store = FakeTaskEvents()
    set_task_events_connector(store)
    monkeypatch.setattr(tasks_router, "paris_now", lambda: NOW)
    return store


def test_tests_never_reach_the_real_calendar_events():
    from app.core.dependencies import get_task_events_connector, get_task_events_connector_error
    assert get_task_events_connector() is None
    assert "test" in get_task_events_connector_error()


def test_adds_a_task_with_hour_and_reminder(events):
    res = client.post("/api/v1/tasks", json={
        "titre": "ORL", "echeance": "2026-11-05", "heure": "14:30", "rappel_minutes_avant": 1440,
    })
    assert res.status_code == 201
    assert (res.json()["heure"], res.json()["rappel_minutes_avant"]) == ("14:30", 1440)
    assert events.events[res.json()["id"]].debut == datetime(2026, 11, 5, 14, 30, tzinfo=APP_TIMEZONE)


def test_hour_without_day_is_refused(events):
    assert client.post("/api/v1/tasks", json={"titre": "ORL", "heure": "14:30"}).status_code == 422


def test_lists_tasks_with_their_hour_and_parent(events):
    events.create_event("t1", "ORL", datetime(2026, 11, 2, 10, 0, tzinfo=APP_TIMEZONE), None)
    body = client.get("/api/v1/tasks").json()
    assert body["taches"][0]["heure"] == "10:00"
    assert body["taches"][1]["parent"] is None


def test_checking_deletes_the_upcoming_event_and_reopen_with_hour_recreates_it(events):
    client.post("/api/v1/tasks", json={"titre": "ORL", "echeance": "2026-11-05", "heure": "14:30"})
    task_id = next(iter(events.events))
    assert client.patch(f"/api/v1/tasks/{task_id}", json={"terminee": True}).status_code == 200
    assert events.events == {}
    res = client.patch(f"/api/v1/tasks/{task_id}", json={"terminee": False, "heure": "14:30"})
    assert res.status_code == 200
    assert res.json()["heure"] == "14:30"
    assert task_id in events.events


def test_hour_is_refused_when_checking(events):
    assert client.patch("/api/v1/tasks/t2", json={"terminee": True, "heure": "14:30"}).status_code == 422


# --- Suppression (refonte UX, étape 7 : « Annuler » de « En faire une tâche » du Second cerveau) ---------------

def test_deletes_a_task(fake):
    res = client.delete("/api/v1/tasks/t2")

    assert res.status_code == 204
    assert [t.id for t in fake.list_open_tasks()] == ["t1"]


def test_deleting_an_unknown_task_answers_502_with_the_google_message(fake):
    res = client.delete("/api/v1/tasks/t9")

    assert res.status_code == 502
    assert "404" in res.json()["detail"] and "t9" in res.json()["detail"]


def test_deleting_a_task_also_deletes_its_calendar_event(fake, events):
    client.post("/api/v1/tasks", json={"titre": "ORL", "echeance": "2026-11-05", "heure": "14:30"})
    task_id = next(iter(events.events))

    assert client.delete(f"/api/v1/tasks/{task_id}").status_code == 204
    assert events.events == {}
    assert task_id not in fake.tasks
