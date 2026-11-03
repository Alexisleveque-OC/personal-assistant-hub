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
