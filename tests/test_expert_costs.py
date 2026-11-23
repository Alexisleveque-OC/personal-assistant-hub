"""Coûts de l'expert Claude (Phase 6.10, étape 3) : tarif par appel, journal `llm_usage`, garde-fou mensuel, consultation."""
import json
import logging
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.factory import set_agent_llm, set_expert_llm
from app.core.agent.tools.escalation_tools import ESCALATION_TOOL_NAME
from app.core.dependencies import set_sport_connector
from app.core.expert.llm import ExpertUsage
from app.core.expert.pricing import usage_cost_usd
from app.main import app
from tests.agent_fakes import ScriptedLLM, call_turn, text_turn
from tests.test_expert_service import ScriptedExpertLLM, text_turn as expert_text


def test_sonnet_cost_counts_input_output_and_cache_tokens():
    usage = ExpertUsage(
        model="claude-sonnet-5-5", input_tokens=1_000_000, output_tokens=100_000,
        cache_read_input_tokens=1_000_000, cache_creation_input_tokens=1_000_000,
    )
    # 2 $ entrée + 1 $ sortie (10 $/M) + 0,10 $ lecture cache + 2,50 $ écriture cache (1,25 × entrée)
    assert usage_cost_usd(usage) == pytest.approx(5.60)


def test_unknown_model_is_priced_at_the_most_expensive_known_rate_with_a_warning(caplog):
    usage = ExpertUsage(model="claude-inconnu", input_tokens=1_000_000)
    with caplog.at_level(logging.WARNING):
        cost = usage_cost_usd(usage)
    assert cost >= 5.0
    assert "claude-inconnu" in caplog.text


def test_monthly_total_only_counts_the_current_month(isolate_sqlite_database):
    db = isolate_sqlite_database
    db.add_llm_usage("claude-sonnet-5-5", 10, 5, 0, 0, 1.25, "s1", created_at="2026-10-31T23:00:00+00:00")
    db.add_llm_usage("claude-sonnet-5-5", 10, 5, 0, 0, 0.40, "s1", created_at="2026-11-02T08:00:00+00:00")
    db.add_llm_usage("claude-sonnet-5-5", 10, 5, 0, 0, 0.10, "s2", created_at="2026-11-23T08:00:00+00:00")

    totals = db.get_llm_usage_totals("2026-11-01T00:00:00+00:00")
    assert totals["cost_usd"] == pytest.approx(0.50)
    assert totals["calls"] == 2


@pytest.fixture
def agent_db(isolate_sqlite_database, monkeypatch):
    monkeypatch.setattr(settings, "nlu_mode", "agent")
    set_sport_connector(SqlSportConnector(db_manager=isolate_sqlite_database))
    yield isolate_sqlite_database
    set_sport_connector(None)
    set_agent_llm(None)


def _ask(query: str) -> dict:
    resp = TestClient(app).post("/api/v1/interact", json={"query": query, "session_id": "cost-test"})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _escalate():
    return call_turn({"name": ESCALATION_TOOL_NAME, "args": {"question": "Porte de frigo"}})


def test_expert_turn_records_its_cost_and_logs_it(agent_db):
    set_agent_llm(ScriptedLLM([_escalate()]))
    set_expert_llm(ScriptedExpertLLM([expert_text("Réponse.")]))  # 100 tokens entrée, 20 sortie

    body = _ask("Comment changer la porte de mon frigo ?")

    expected = (100 * 2 + 20 * 10) / 1_000_000
    assert body["data"]["expert"]["cost_usd"] == pytest.approx(expected)
    with agent_db.get_connection() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM llm_usage")]
    assert len(rows) == 1
    assert (rows[0]["model"], rows[0]["input_tokens"], rows[0]["output_tokens"]) == ("claude-sonnet-5-5", 100, 20)
    assert rows[0]["cost_usd"] == pytest.approx(expected)
    assert rows[0]["session_id"] == "cost-test"


def test_exhausted_monthly_budget_leaves_gemini_alone_and_says_why(agent_db, monkeypatch):
    monkeypatch.setattr(settings, "claude_monthly_budget_usd", 5.0)
    agent_db.add_llm_usage("claude-sonnet-5-5", 0, 0, 0, 0, 5.0, "s", created_at=datetime.now(timezone.utc).isoformat())
    gemini = ScriptedLLM([text_turn("Je fais au mieux.")])
    set_agent_llm(gemini)
    claude = ScriptedExpertLLM([])
    set_expert_llm(claude)

    body = _ask("Comment changer la porte de mon frigo ?")

    assert body["spoken_response"] == "Je fais au mieux."
    assert ESCALATION_TOOL_NAME not in {t["name"] for t in gemini.requests[0]["tools"]}
    assert "budget" in body["data"]["expert_disabled"]
    assert claude.requests == []


def test_usage_endpoint_reports_the_month_against_the_budget(isolate_sqlite_database, monkeypatch):
    monkeypatch.setattr(settings, "claude_monthly_budget_usd", 5.0)
    isolate_sqlite_database.add_llm_usage(
        "claude-sonnet-5-5", 0, 0, 0, 0, 1.5, "s", created_at=datetime.now(timezone.utc).isoformat(),
    )

    body = TestClient(app).get("/api/v1/system/expert-usage").json()

    assert body == {"month_cost_usd": 1.5, "budget_usd": 5.0, "remaining_usd": 3.5, "calls": 1}


def test_expert_failure_still_records_the_billed_calls(agent_db):
    set_agent_llm(ScriptedLLM([_escalate()]))
    set_expert_llm(ScriptedExpertLLM([expert_text("   ")]))  # réponse vide : facturée puis rejetée

    body = _ask("Comment changer la porte de mon frigo ?")

    assert "vide" in body["data"]["error"]
    assert body["data"]["expert"]["usages"][0]["output_tokens"] == 20
    with agent_db.get_connection() as conn:
        log = conn.execute("SELECT parameters FROM conversation_logs ORDER BY id DESC LIMIT 1").fetchone()[0]
        assert conn.execute("SELECT COUNT(*) FROM llm_usage").fetchone()[0] == 1
    assert json.loads(log)["expert"]["cost_usd"] > 0
