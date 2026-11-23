"""Cascade Gemini → expert Claude branchée dans /interact (mode agent), avec des LLM scriptés hors ligne."""
import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.factory import set_agent_llm, set_expert_llm
from app.core.agent.tools.escalation_tools import ESCALATION_TOOL_NAME
from app.core.dependencies import set_sport_connector
from app.core.expert.errors import ExpertUnavailableError
from app.core.session_manager import get_session_manager
from app.main import app
from tests.agent_fakes import ScriptedLLM, call_turn, text_turn
from tests.test_expert_service import ScriptedExpertLLM, text_turn as expert_text


@pytest.fixture
def db(isolate_sqlite_database, monkeypatch):
    monkeypatch.setattr(settings, "nlu_mode", "agent")
    set_sport_connector(SqlSportConnector(db_manager=isolate_sqlite_database))
    yield isolate_sqlite_database
    set_sport_connector(None)
    set_agent_llm(None)


def _ask(query: str, session_id: str = "expert-test") -> dict:
    resp = TestClient(app).post("/api/v1/interact", json={"query": query, "session_id": session_id})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _last_log(db) -> dict:
    with db.get_connection() as conn:
        return dict(conn.execute("SELECT * FROM conversation_logs ORDER BY id DESC LIMIT 1").fetchone())


def _escalate():
    return call_turn({"name": ESCALATION_TOOL_NAME, "args": {"question": "Changer une porte de frigo"}})


def test_without_anthropic_key_the_expert_is_not_offered_to_gemini(db):
    gemini = ScriptedLLM([text_turn("Je ne sais pas trop.")])
    set_agent_llm(gemini)

    body = _ask("Comment changer la porte de mon frigo ?")

    assert body["spoken_response"] == "Je ne sais pas trop."
    assert ESCALATION_TOOL_NAME not in {t["name"] for t in gemini.requests[0]["tools"]}
    assert body["data"]["level"] == "agent"


def test_escalated_question_is_answered_by_the_expert_and_logged(db):
    set_agent_llm(ScriptedLLM([_escalate()]))
    set_expert_llm(ScriptedExpertLLM([expert_text("Relève la référence sur la plaque du frigo.")]))

    body = _ask("Comment changer la porte de mon frigo ?")

    assert body["success"] is True
    assert body["spoken_response"] == "Relève la référence sur la plaque du frigo."
    assert body["data"]["level"] == "expert"
    assert body["data"]["expert"]["reason"] == "demande"
    assert body["data"]["expert"]["model"] == "claude-sonnet-5-5"
    params = json.loads(_last_log(db)["parameters"])
    assert params["level"] == "expert"
    assert params["expert"]["usages"][0]["output_tokens"] == 20
    history = get_session_manager().get_session("expert-test")["history"]
    assert history[-1]["text"] == "Relève la référence sur la plaque du frigo."


def test_answer_to_an_expert_question_goes_straight_back_to_the_expert(db):
    gemini = ScriptedLLM([_escalate()])
    set_agent_llm(gemini)
    claude = ScriptedExpertLLM([expert_text("Quelle est la marque du frigo ?"), expert_text("Pour un Bosch, …")])
    set_expert_llm(claude)

    _ask("Comment changer la porte de mon frigo ?")
    body = _ask("Bosch")

    assert body["spoken_response"] == "Pour un Bosch, …"
    assert body["data"]["expert"]["reason"] == "suite"
    assert len(gemini.requests) == 1
    assert claude.requests[1]["messages"][-1]["content"] == "Bosch"


def test_expert_unavailable_gives_an_explicit_answer(db):
    set_agent_llm(ScriptedLLM([_escalate()]))
    set_expert_llm(ScriptedExpertLLM([ExpertUnavailableError("Crédit Anthropic épuisé (HTTP 400).")]))

    body = _ask("Comment changer la porte de mon frigo ?")

    assert "expert" in body["spoken_response"].lower()
    assert "indisponible" in body["spoken_response"]
    assert "Crédit Anthropic épuisé" in body["data"]["error"]


def test_deepen_request_goes_straight_to_the_expert_for_a_detailed_answer(db):
    gemini = ScriptedLLM([_escalate()])
    set_agent_llm(gemini)
    claude = ScriptedExpertLLM([expert_text("Réponse courte."), expert_text("1. Relève la référence. 2. …")])
    set_expert_llm(claude)

    _ask("Comment changer la porte de mon frigo ?")
    resp = TestClient(app).post("/api/v1/interact", json={
        "query": "Approfondis", "session_id": "expert-test", "context": {"expert_detailed": True},
    })
    body = resp.json()

    assert body["data"]["expert"]["reason"] == "approfondir"
    assert body["spoken_response"].startswith("1. Relève")
    assert len(gemini.requests) == 1
    assert claude.requests[1]["max_tokens"] > claude.requests[0]["max_tokens"]
    assert "expert_detailed" not in get_session_manager().get_session("expert-test")


def test_expert_only_gets_the_light_follow_up_tools(db):
    set_agent_llm(ScriptedLLM([_escalate()]))
    claude = ScriptedExpertLLM([expert_text("Réponse.")])
    set_expert_llm(claude)

    _ask("Comment changer la porte de mon frigo ?")

    names = {t["name"] for t in claude.requests[0]["tools"]}
    assert names == {"add_task", "get_tasks", "get_agenda", "add_shopping_items", "save_note"}


def test_an_answer_more_than_10_minutes_after_the_expert_question_goes_back_to_gemini(db):
    gemini = ScriptedLLM([_escalate(), text_turn("C'est noté.")])
    set_agent_llm(gemini)
    claude = ScriptedExpertLLM([expert_text("Quelle est la marque du frigo ?")])
    set_expert_llm(claude)

    _ask("Comment changer la porte de mon frigo ?")
    session = get_session_manager().get_session("expert-test")
    session["expert_awaiting_reply"] -= 601  # la question de l'expert date de plus de 10 minutes
    body = _ask("Bosch")

    assert body["spoken_response"] == "C'est noté."
    assert body["data"]["level"] == "agent"
    assert len(claude.requests) == 1
