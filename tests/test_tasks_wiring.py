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


def test_remind_me_adds_a_google_task_that_undo_removes(isolate_sqlite_database, monkeypatch):
    """« Rappelle-moi de… » : vraie tâche Google (plus la confirmation fictive du flux regex), « annule ça » la supprime."""
    from tests.test_tasks_write_tools import FakeWritableTasks

    monkeypatch.setattr(settings, "nlu_mode", "agent")
    set_sport_connector(SqlSportConnector(db_manager=isolate_sqlite_database))
    store = FakeWritableTasks()
    set_tasks_connector(store)
    set_agent_llm(ScriptedLLM([
        call_turn({"name": "add_task", "args": {"titre": "Appeler la banque", "echeance": "2026-11-04"}}),
        text_turn("C'est ajouté à tes tâches pour demain."),
    ]))
    client = TestClient(app)
    try:
        resp = client.post("/api/v1/interact", json={"query": "Rappelle-moi d'appeler la banque demain", "session_id": "tasks-add"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["spoken_response"] == "C'est ajouté à tes tâches pour demain."
        assert [(t.titre, str(t.echeance)) for t in store.list_open_tasks()] == [("Appeler la banque", "2026-11-04")]

        undo = client.post("/api/v1/interact", json={"query": "annule ça", "session_id": "tasks-add"})
        assert undo.status_code == 200, undo.text
        assert "tâche « Appeler la banque » supprimée" in undo.json()["spoken_response"]
        assert store.tasks == {}
    finally:
        set_sport_connector(None)
        set_agent_llm(None)
