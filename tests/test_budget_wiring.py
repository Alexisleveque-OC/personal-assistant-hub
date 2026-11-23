"""Câblage du Budget (Phase 10, étape 2) : connecteur depuis les réglages, outils de lecture branchés dans /interact."""
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.connectors.sheets.budget_connector import BudgetConnector
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.factory import EXPERT_TOOL_NAMES, set_agent_llm
from app.core.agent.prompt import build_system_prompt
from app.core.dependencies import get_budget_connector, get_budget_connector_error, set_budget_connector, set_sport_connector
from app.main import app
from tests.agent_fakes import ScriptedLLM, call_turn, text_turn
from tests.budget_fakes import BudgetSheetState, build_budget_spreadsheet

BUDGET_TOOLS = {"get_budget_remaining", "get_income", "get_installments"}


def test_tests_never_reach_the_real_budget_sheet() -> None:
    assert get_budget_connector() is None
    assert "test" in get_budget_connector_error()


@pytest.fixture
def agent_with_budget(isolate_sqlite_database, monkeypatch):
    monkeypatch.setattr(settings, "nlu_mode", "agent")
    set_sport_connector(SqlSportConnector(db_manager=isolate_sqlite_database))
    set_budget_connector(BudgetConnector(build_budget_spreadsheet(BudgetSheetState())))
    yield
    set_sport_connector(None)
    set_agent_llm(None)


def test_interact_answers_the_remaining_question_through_the_budget_tool(agent_with_budget) -> None:
    llm = ScriptedLLM([
        call_turn({"name": "get_budget_remaining", "args": {"categorie": "course"}}),
        text_turn("Il reste 412 euros en Course."),
    ])
    set_agent_llm(llm)

    resp = TestClient(app).post(
        "/api/v1/interact", json={"query": "Combien il reste en course ?", "session_id": "budget"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["spoken_response"] == "Il reste 412 euros en Course."
    assert BUDGET_TOOLS <= {t["name"] for t in llm.requests[0]["tools"]}
    assert "412.5" in str(llm.requests[1]["contents"])


def test_budget_tools_are_not_given_to_the_claude_expert() -> None:
    assert not BUDGET_TOOLS & EXPERT_TOOL_NAMES


def test_prompt_has_budget_rules() -> None:
    from datetime import date
    prompt = build_system_prompt(date(2026, 11, 23), [])
    assert "get_budget_remaining" in prompt
    assert "ce mois-ci" in prompt


@pytest.mark.parametrize("query", [
    "Combien il reste en course ?",
    "Quel est le solde du budget loisir ?",
    "J'ai dépensé 20 euros en restaurant",
])
def test_legacy_fake_budget_replies_are_routed_to_the_agent(agent_with_budget, query) -> None:
    """Le flux regex répondait des montants fictifs (« 145 euros ») : le budget passe toujours par l'agent."""
    set_agent_llm(ScriptedLLM([text_turn("Réponse de l'agent.")]))
    resp = TestClient(app).post("/api/v1/interact", json={"query": query, "session_id": "budget-legacy"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["spoken_response"] == "Réponse de l'agent."
