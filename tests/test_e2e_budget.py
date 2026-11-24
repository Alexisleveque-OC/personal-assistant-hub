"""E2E Phase 10 (étape 5) : Budget de bout en bout, d'une conversation à la voix jusqu'au classeur.

Phrases → /interact → agent (LLM scripté) → outils budget → VRAI `BudgetConnector` → faux classeur (onglets pleins,
comme le vrai le 24/11) ; lecture après écriture dans la même conversation (invalidation du cache), puis annulation
de chaque écriture depuis « Dernières actions » de l'accueil : le classeur revient exactement à son état initial.
"""
import copy

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.connectors.sheets.budget_connector import BudgetConnector
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.factory import set_agent_llm
from app.core.dependencies import set_budget_connector, set_sport_connector
from app.core.session_manager import get_session_manager
from app.main import app
from tests.agent_fakes import ScriptedLLM, call_turn, text_turn
from tests.budget_fakes import BudgetSheetState, build_budget_spreadsheet

SESSION = "e2e-budget"
WRITTEN_TABS = ("Débit", "Swile", "Revenus", "Échéanciers", "Dépenses Multiples")


@pytest.fixture
def full_budget(isolate_sqlite_database, monkeypatch):
    monkeypatch.setattr(settings, "nlu_mode", "agent")
    set_sport_connector(SqlSportConnector(db_manager=isolate_sqlite_database))
    spreadsheet = build_budget_spreadsheet(BudgetSheetState(spare_rows=0))
    set_budget_connector(BudgetConnector(spreadsheet))
    yield spreadsheet
    get_session_manager().clear_all()
    set_sport_connector(None)
    set_agent_llm(None)


def _ask(client: TestClient, query: str) -> dict:
    resp = client.post("/api/v1/interact", json={"query": query, "session_id": SESSION})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _data(spreadsheet, tab):
    return spreadsheet.worksheet(tab).rows[1:]


def test_budget_conversation_writes_reads_back_and_is_fully_undone(full_budget) -> None:
    spreadsheet = full_budget
    initial = {tab: copy.deepcopy(spreadsheet.worksheet(tab).rows) for tab in WRITTEN_TABS}
    llm = ScriptedLLM([
        call_turn({"name": "get_budget_remaining", "args": {"categorie": "course"}}),
        text_turn("Il reste 412 euros en Course."),
        call_turn({"name": "get_installments", "args": {}}),
        text_turn("Aucun échéancier en cours."),
        call_turn({"name": "add_expense", "args": {"montant": 9.5, "categorie": "course", "libelle": "sandwich",
                                                   "swile": True}}),
        text_turn("9,50 euros en Swile, Course."),
        call_turn({"name": "add_expense", "args": {"montant": 20, "categorie": "restaurant", "libelle": "resto",
                                                   "remboursement": True}}),
        text_turn("Remboursement de 20 euros noté."),
        call_turn({"name": "add_income", "args": {"montant": 150, "type": "caf", "libelle": "caf"}}),
        text_turn("150 euros de CAF notés."),
        call_turn({"name": "add_installment", "args": {"nom": "ikea", "montant_total": 400, "nb_echeances": 4,
                                                       "categorie": "course"}}),
        text_turn("Échéancier créé : 4 fois 100 euros."),
        call_turn({"name": "get_installments", "args": {}}),
        text_turn("Un échéancier : ikea."),
        call_turn({"name": "predeclare_split_expense", "args": {"mot_cle": "amazon", "montant_total": 50, "parts": [
            {"categorie": "course", "montant": 30}, {"categorie": "chats", "montant": 20}]}}),
        text_turn("Dépense multiple notée."),
    ])
    set_agent_llm(llm)
    client = TestClient(app)

    _ask(client, "Combien il reste en course ?")
    assert "412.5" in str(llm.requests[1]["contents"])
    _ask(client, "Où en sont mes échéanciers ?")  # met « Échéanciers » en cache avant l'écriture
    empty = llm.requests[-1]["contents"][-1]["parts"][0]["functionResponse"]
    assert empty["name"] == "get_installments" and "ikea" not in str(empty["response"])
    log_ids = [
        _ask(client, "J'ai payé un sandwich 9,50 en Swile en course")["data"]["log_id"],
        _ask(client, "Je me suis fait rembourser 20 euros de resto")["data"]["log_id"],
        _ask(client, "J'ai touché 150 euros de CAF")["data"]["log_id"],
        _ask(client, "J'ai payé 400 euros en 4 fois chez Ikea en course")["data"]["log_id"],
    ]
    _ask(client, "Et mes échéanciers maintenant ?")
    listed = llm.requests[-1]["contents"][-1]["parts"][0]["functionResponse"]
    assert listed["name"] == "get_installments"
    assert "ikea" in str(listed["response"]), "le cache des échéanciers n'a pas été invalidé par l'écriture"
    log_ids.append(_ask(client, "Dépense d'avance de 50 euros chez Amazon, 30 en course et 20 en chats")["data"]["log_id"])

    assert [row[1:] for row in _data(spreadsheet, "Swile")] == [[9.5, "Course", "Otis : sandwich"]]
    assert [row[1:] for row in _data(spreadsheet, "Débit")] == [[-20, "Restaurant", "", "Otis : resto"]]
    assert [row[1:] for row in _data(spreadsheet, "Revenus")] == [[150, "CAF", "", "Otis : caf"]]
    assert [row[:5] for row in _data(spreadsheet, "Échéanciers")] == [["ikea", 400, 4, 0, 100.0]]
    assert _data(spreadsheet, "Dépenses Multiples")[0][1:4] == ["amazon", 50, "A traiter"]

    for log_id in reversed(log_ids):
        resp = client.post(f"/api/v1/home/recent-actions/{log_id}/undo", params={"session_id": SESSION})
        assert resp.status_code == 200, resp.text

    assert {tab: spreadsheet.worksheet(tab).rows for tab in WRITTEN_TABS} == initial
