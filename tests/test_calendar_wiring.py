"""Câblage de l'Agenda Google (Phase 8, étape 1) : connecteur construit depuis les réglages, outil branché dans /interact."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.connectors.calendar.calendar_connector import CalendarConnector
from app.connectors.google_oauth import GoogleOAuthNotConfiguredError
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.factory import set_agent_llm
from app.core.dependencies import (
    get_calendar_connector,
    get_calendar_connector_error,
    set_calendar_connector,
    set_sport_connector,
)
from app.main import app
from tests.agent_fakes import ScriptedLLM, call_turn, text_turn
from tests.test_calendar_agent_tools import DENTISTE, FakeCalendar


def test_tests_never_reach_the_real_calendar():
    assert get_calendar_connector() is None
    assert "test" in get_calendar_connector_error()


def test_connector_is_built_from_the_oauth_settings(monkeypatch):
    monkeypatch.setattr(settings, "google_oauth_client_id", "id")
    monkeypatch.setattr(settings, "google_oauth_client_secret", "secret")
    monkeypatch.setattr(settings, "google_oauth_refresh_token", "refresh")
    assert isinstance(CalendarConnector.from_settings(settings), CalendarConnector)


def test_missing_refresh_token_is_reported(monkeypatch):
    monkeypatch.setattr(settings, "google_oauth_client_id", "id")
    monkeypatch.setattr(settings, "google_oauth_client_secret", "secret")
    monkeypatch.setattr(settings, "google_oauth_refresh_token", "")
    with pytest.raises(GoogleOAuthNotConfiguredError, match="GOOGLE_OAUTH_REFRESH_TOKEN"):
        CalendarConnector.from_settings(settings)


@pytest.fixture
def agent_with_calendar(isolate_sqlite_database, monkeypatch):
    monkeypatch.setattr(settings, "nlu_mode", "agent")
    set_sport_connector(SqlSportConnector(db_manager=isolate_sqlite_database))
    calendar = FakeCalendar([DENTISTE])
    set_calendar_connector(calendar)
    yield calendar
    set_sport_connector(None)
    set_agent_llm(None)


def test_interact_answers_the_agenda_question_through_get_agenda(agent_with_calendar):
    llm = ScriptedLLM([
        call_turn({"name": "get_agenda", "args": {"date_debut": "2026-10-30"}}),
        text_turn("Demain, tu as le dentiste à 14 h."),
    ])
    set_agent_llm(llm)

    resp = TestClient(app).post("/api/v1/interact", json={"query": "Qu'est-ce que j'ai demain ?", "session_id": "agenda"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["spoken_response"] == "Demain, tu as le dentiste à 14 h."
    assert agent_with_calendar.calls == [(date(2026, 10, 30), date(2026, 10, 30))]
    declared = {t["name"] for t in llm.requests[0]["tools"]}
    assert "get_agenda" in declared
    assert "Dentiste" in str(llm.requests[1]["contents"])
