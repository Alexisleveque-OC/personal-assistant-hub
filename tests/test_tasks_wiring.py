"""Câblage de Google Tasks (Phase 8, étape 3) : connecteur construit depuis les réglages, outil branché dans /interact."""
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.connectors.google_oauth import GoogleOAuthNotConfiguredError
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.connectors.tasks.tasks_connector import TasksConnector
from app.core.agent.factory import set_agent_llm
from app.core.dependencies import (
    get_tasks_connector,
    get_tasks_connector_error,
    set_sport_connector,
    set_tasks_connector,
)
from app.main import app
from tests.agent_fakes import ScriptedLLM, call_turn, text_turn
from tests.test_tasks_agent_tools import CANTINE, FakeTasks


def test_tests_never_reach_the_real_tasks():
    assert get_tasks_connector() is None
    assert "test" in get_tasks_connector_error()


def test_connector_is_built_from_the_oauth_settings(monkeypatch):
    monkeypatch.setattr(settings, "google_oauth_client_id", "id")
    monkeypatch.setattr(settings, "google_oauth_client_secret", "secret")
    monkeypatch.setattr(settings, "google_oauth_refresh_token", "refresh")
    assert isinstance(TasksConnector.from_settings(settings), TasksConnector)


def test_missing_refresh_token_is_reported(monkeypatch):
    monkeypatch.setattr(settings, "google_oauth_client_id", "id")
    monkeypatch.setattr(settings, "google_oauth_client_secret", "secret")
    monkeypatch.setattr(settings, "google_oauth_refresh_token", "")
    with pytest.raises(GoogleOAuthNotConfiguredError, match="GOOGLE_OAUTH_REFRESH_TOKEN"):
        TasksConnector.from_settings(settings)


@pytest.fixture
def agent_with_tasks(isolate_sqlite_database, monkeypatch):
    monkeypatch.setattr(settings, "nlu_mode", "agent")
    set_sport_connector(SqlSportConnector(db_manager=isolate_sqlite_database))
    tasks = FakeTasks([CANTINE])
    set_tasks_connector(tasks)
    yield tasks
    set_sport_connector(None)
    set_agent_llm(None)


def test_interact_answers_the_tasks_question_through_get_tasks(agent_with_tasks):
    llm = ScriptedLLM([
        call_turn({"name": "get_tasks", "args": {}}),
        text_turn("Tu dois payer la cantine jeudi."),
    ])
    set_agent_llm(llm)

    resp = TestClient(app).post("/api/v1/interact", json={"query": "Liste-moi mes tâches", "session_id": "tasks"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["spoken_response"] == "Tu dois payer la cantine jeudi."
    assert agent_with_tasks.calls == 1
    declared = {t["name"] for t in llm.requests[0]["tools"]}
    assert {"get_tasks", "get_agenda"} <= declared
    assert "Payer la cantine" in str(llm.requests[1]["contents"])


def test_remind_me_no_longer_gets_the_fake_legacy_confirmation(agent_with_tasks):
    """L'ancien flux regex répondait « Tâche enregistrée » sans rien enregistrer : la phrase va désormais à l'agent."""
    llm = ScriptedLLM([text_turn("Je ne sais pas encore ajouter de tâche.")])
    set_agent_llm(llm)

    resp = TestClient(app).post(
        "/api/v1/interact", json={"query": "Rappelle-moi d'appeler la banque", "session_id": "tasks-add"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["spoken_response"] == "Je ne sais pas encore ajouter de tâche."
    assert len(llm.requests) == 1
