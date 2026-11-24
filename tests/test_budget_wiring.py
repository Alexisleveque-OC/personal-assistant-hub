"""Câblage du Budget (Phase 10, étapes 2-3) : connecteur depuis les réglages, outils branchés dans /interact."""
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.connectors.sheets.budget_connector import BudgetConnector
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.factory import EXPERT_TOOL_NAMES, set_agent_llm
from app.core.agent.prompt import build_system_prompt
from app.core.dependencies import get_budget_connector, get_budget_connector_error, set_budget_connector, set_sport_connector
from app.core.home.recent_actions import action_label
from app.core.session_manager import get_session_manager
from app.main import app
from tests.agent_fakes import ScriptedLLM, call_turn, text_turn
from tests.budget_fakes import BudgetSheetState, build_budget_spreadsheet

BUDGET_TOOLS = {
    "get_budget_remaining", "get_income", "get_installments", "add_expense", "add_income", "correct_budget_category",
    "add_installment", "predeclare_split_expense",
}


def test_tests_never_reach_the_real_budget_sheet() -> None:
    assert get_budget_connector() is None
    assert "test" in get_budget_connector_error()


@pytest.fixture
def agent_with_budget(isolate_sqlite_database, monkeypatch):
    monkeypatch.setattr(settings, "nlu_mode", "agent")
    set_sport_connector(SqlSportConnector(db_manager=isolate_sqlite_database))
    spreadsheet = build_budget_spreadsheet(BudgetSheetState())
    set_budget_connector(BudgetConnector(spreadsheet))
    yield spreadsheet
    get_session_manager().clear_all()
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


def test_prompt_has_budget_write_rules() -> None:
    from datetime import date
    prompt = build_system_prompt(date(2026, 11, 23), [])
    for expected in ("add_expense", "add_income", "correct_budget_category", "remboursement", "swile"):
        assert expected in prompt


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


def _ask(query: str, session_id: str = "budget-write") -> dict:
    resp = TestClient(app).post("/api/v1/interact", json={"query": query, "session_id": session_id})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _debit_rows(spreadsheet):
    return spreadsheet.worksheet("Débit").rows[1:]


def test_expense_then_correction_then_undo_through_interact(agent_with_budget) -> None:
    spreadsheet = agent_with_budget
    set_agent_llm(ScriptedLLM([
        call_turn({"name": "add_expense", "args": {"montant": 23.5, "categorie": "course", "libelle": "pizza"}}),
        text_turn("23,50 euros en Course, c'est noté."),
        call_turn({"name": "correct_budget_category", "args": {"categorie": "restaurant"}}),
        text_turn("Corrigé : Restaurant."),
        call_turn({"name": "undo_last_action", "args": {}}),
        text_turn("La correction est annulée."),
    ]))

    _ask("J'ai dépensé 23,50 en course pour une pizza")
    assert [row[1:] for row in _debit_rows(spreadsheet)] == [[23.5, "Course", "", "Otis : pizza"]]
    _ask("Non, c'était dans la catégorie restaurant")
    assert _debit_rows(spreadsheet)[0][2] == "Restaurant"
    _ask("Annule")
    assert _debit_rows(spreadsheet)[0][2] == "Course"


def test_recent_action_undo_deletes_the_budget_line(agent_with_budget) -> None:
    spreadsheet = agent_with_budget
    set_agent_llm(ScriptedLLM([
        call_turn({"name": "add_expense", "args": {"montant": 8, "categorie": "chats", "libelle": "croquettes"}}),
        text_turn("C'est noté."),
    ]))
    log_id = _ask("J'ai dépensé 8 euros en chats")["data"]["log_id"]

    resp = TestClient(app).post(f"/api/v1/home/recent-actions/{log_id}/undo", params={"session_id": "budget-write"})

    assert resp.status_code == 200, resp.text
    assert _debit_rows(spreadsheet) == []


@pytest.mark.parametrize("tool, args, label", [
    ("add_expense", {"montant": 8, "categorie": "chats"}, "Dépense enregistrée : 8 € en chats"),
    ("add_expense", {"montant": 20, "categorie": "santé", "remboursement": True}, "Remboursement enregistré : 20 € en santé"),
    ("add_income", {"montant": 150, "type": "CAF"}, "Revenu enregistré : 150 € en CAF"),
    ("correct_budget_category", {"categorie": "restaurant"}, "Catégorie corrigée : restaurant"),
])
def test_budget_writes_have_a_recent_action_label(tool, args, label) -> None:
    log = {"intent": "agent", "parameters": {"tool_calls": [{"name": tool, "args": args}]}}
    assert action_label(log) == label


def test_installment_and_split_then_undo_through_interact(agent_with_budget) -> None:
    spreadsheet = agent_with_budget
    set_agent_llm(ScriptedLLM([
        call_turn({"name": "add_installment", "args": {
            "nom": "ikea", "montant_total": 400, "nb_echeances": 4, "categorie": "course"}}),
        text_turn("Échéancier créé : 4 fois 100 euros."),
        call_turn({"name": "predeclare_split_expense", "args": {"mot_cle": "amazon", "montant_total": 50, "parts": [
            {"categorie": "course", "montant": 30}, {"categorie": "chats", "montant": 20}]}}),
        text_turn("Dépense multiple notée."),
        call_turn({"name": "undo_last_action", "args": {}}),
        text_turn("Annulé."),
    ]))

    _ask("J'ai payé 400 euros en 4 fois chez Ikea en course", "budget-plans")
    assert [row[:5] for row in spreadsheet.worksheet("Échéanciers").rows[1:]] == [["ikea", 400, 4, 0, 100.0]]
    _ask("Dépense d'avance de 50 euros chez Amazon, 30 en course et 20 en chats", "budget-plans")
    assert spreadsheet.worksheet("Dépenses Multiples").rows[1][1:4] == ["amazon", 50, "A traiter"]
    _ask("Annule", "budget-plans")
    assert spreadsheet.worksheet("Dépenses Multiples").rows[1:] == []
    assert len(spreadsheet.worksheet("Échéanciers").rows) == 2
