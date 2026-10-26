"""Tests du branchement de l'agent dans /interact derrière l'interrupteur NLU_MODE (Phase 6.8 - Étape 3)."""
from datetime import date
import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.errors import AgentUnavailableError
from app.core.agent.factory import set_agent_llm
from app.core.dependencies import set_sport_connector
from app.core.session_manager import get_session_manager
from app.main import app
from tests.agent_fakes import ScriptedLLM, call_turn, text_turn

TODAY = date.today().isoformat()


@pytest.fixture
def db(isolate_sqlite_database):
    set_sport_connector(SqlSportConnector(db_manager=isolate_sqlite_database))
    yield isolate_sqlite_database
    set_sport_connector(None)
    set_agent_llm(None)


@pytest.fixture
def agent_mode(monkeypatch):
    monkeypatch.setattr(settings, "nlu_mode", "agent")


def _ask(query: str, session_id: str = "agent-test") -> dict:
    resp = TestClient(app).post("/api/v1/interact", json={"query": query, "session_id": session_id})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _last_log(db) -> dict:
    with db.get_connection() as conn:
        return dict(conn.execute("SELECT * FROM conversation_logs ORDER BY id DESC LIMIT 1").fetchone())


def test_default_mode_is_legacy():
    from app.config import Settings
    assert Settings(_env_file=None).nlu_mode == "legacy"


def test_sport_request_goes_through_agent(db, agent_mode):
    session_id = db.add_sport_session({"date": TODAY, "type_seance": "EF", "statut": "Réalisé"})
    llm = ScriptedLLM([
        call_turn({"name": "update_sport_session", "args": {"session_id": session_id, "changes": {"ressenti_rpe": 5}}}),
        text_turn("C'est noté, RPE 5 pour ton footing du jour."),
    ])
    set_agent_llm(llm)

    body = _ask("Mets le RPE de ma séance du jour à 5")

    assert body["success"] is True
    assert body["spoken_response"] == "C'est noté, RPE 5 pour ton footing du jour."
    assert body["intent"]["intent"] == "agent"
    assert body["data"]["session"]["id"] == session_id
    assert body["data"]["tool_calls"][0]["name"] == "update_sport_session"
    assert db.get_sport_session_by_id(session_id)["ressenti_rpe"] == 5

    log = _last_log(db)
    assert (log["intent"], log["success"]) == ("agent", 1)
    assert json.loads(log["parameters"])["tool_calls"][0]["name"] == "update_sport_session"

    history = get_session_manager().get_session("agent-test")["history"]
    assert [h["role"] for h in history[-2:]] == ["user", "assistant"]


def test_unknown_request_goes_to_agent_with_history(db, agent_mode):
    llm = ScriptedLLM([text_turn("Première réponse."), text_turn("Je parlais bien du renfo, tu as raison.")])
    set_agent_llm(llm)

    _ask("Bonjour Otis, comment vas-tu ?", session_id="agent-history")
    _ask("Euh non, je parlais de l'autre truc", session_id="agent-history")

    second_contents = llm.requests[1]["contents"]
    assert [c["role"] for c in second_contents] == ["user", "model", "user"]


def test_fast_path_shopping_and_meals_stay_on_legacy(db, agent_mode, isolate_test_environment):
    set_agent_llm(ScriptedLLM([]))  # tout appel au LLM ferait échouer le test

    add = _ask("Ajoute mouchoirs")
    meals = _ask("Qu'est-ce qu'on mange aujourd'hui ?")

    assert add["intent"]["intent"] == "add_shopping_item"
    assert meals["intent"]["intent"] == "get_meal_plan"


def test_legacy_mode_never_calls_the_agent(db, monkeypatch):
    monkeypatch.setattr(settings, "nlu_mode", "legacy")
    db.add_sport_session({"date": TODAY, "type_seance": "EF", "statut": "Réalisé"})
    set_agent_llm(ScriptedLLM([]))

    body = _ask("Mets le RPE de ma séance d'aujourd'hui à 5")

    assert body["intent"]["intent"] == "update_sport_session"


def test_agent_unavailable_gives_explicit_answer_without_legacy_fallback(db, agent_mode):
    session_id = db.add_sport_session({"date": TODAY, "type_seance": "EF", "statut": "Réalisé"})
    set_agent_llm(ScriptedLLM([AgentUnavailableError("Aucun modèle Gemini disponible : m1 : HTTP 503.")]))

    body = _ask("Mets le RPE de ma séance d'aujourd'hui à 5")

    assert body["success"] is False
    assert "indisponible" in body["spoken_response"]
    assert db.get_sport_session_by_id(session_id)["ressenti_rpe"] is None
    assert "HTTP 503" in _last_log(db)["error_trace"]


def test_failure_after_a_mutation_is_reported_to_the_user(db, agent_mode):
    session_id = db.add_sport_session({"date": TODAY, "type_seance": "EF", "statut": "Réalisé"})
    set_agent_llm(ScriptedLLM([
        call_turn({"name": "update_sport_session", "args": {"session_id": session_id, "changes": {"ressenti_rpe": 6}}}),
        AgentUnavailableError("Aucun modèle Gemini disponible."),
    ]))

    body = _ask("RPE 6 pour aujourd'hui")

    assert body["success"] is False
    assert "1 modification" in body["spoken_response"]
    assert body["data"]["session"]["id"] == session_id


def test_note_saved_by_agent_exposes_note_id_for_undo_toast(db, agent_mode):
    set_agent_llm(ScriptedLLM([
        call_turn({"name": "save_note", "args": {"content": "Revoir le ciblage des séances", "category": "bug_report"}}),
        text_turn("C'est noté dans tes bugs."),
    ]))

    body = _ask("Prends note de ces derniers échanges, il faudra corriger")

    assert body["data"]["note_id"] is not None
    assert body["data"]["category"] == "bug_report"


def test_add_sentence_about_sport_goes_to_agent_not_shopping(db, agent_mode, isolate_test_environment):
    """« Ajoute une séance… » est classé add_shopping_item par les regex : il ne doit jamais finir en courses."""
    set_agent_llm(ScriptedLLM([text_turn("Quel type de séance et pour quel jour ?")]))

    body = _ask("Ajoute une séance de fractionné demain")

    assert body["intent"]["intent"] == "agent"
    isolate_test_environment.add_shopping_item.assert_not_called()
    isolate_test_environment.add_shopping_items.assert_not_called()
