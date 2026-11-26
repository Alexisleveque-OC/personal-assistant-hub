"""Phase 10, étape 7c : formulaires Échéancier et Dépense multiple de l'écran Budget (faux classeur).

POST /api/v1/budget/installments et /api/v1/budget/split-expenses : mêmes écritures que la voix (format des
formulaires de l'Apps Script), saisie inscrite au journal → « Dernières actions » et toast « Annuler » (décisions 26/11).
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.connectors.sheets.budget_connector import BudgetConnector
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.dependencies import set_budget_connector, set_sport_connector
from app.main import app
from tests.budget_fakes import BudgetSheetState, build_budget_spreadsheet

client = TestClient(app)
SESSION = "pwa-1"


def install():
    sheet = build_budget_spreadsheet(BudgetSheetState())
    set_budget_connector(BudgetConnector(sheet, today=lambda: date(2026, 11, 25)))
    return sheet


def rows(sheet, title):
    values = sheet.worksheet(title).get_all_values(value_render_option="UNFORMATTED_VALUE")[1:]
    return [r for r in values if any(str(c).strip() for c in r)]


@pytest.fixture
def sport(isolate_sqlite_database):
    """Le service d'annulation exige le carnet Sport (toujours présent en production)."""
    set_sport_connector(SqlSportConnector(db_manager=isolate_sqlite_database))
    yield
    set_sport_connector(None)


def installment(**body):
    payload = {"nom": "ikea", "montant_total": 400, "nb_echeances": 4, "categorie": "Loisir Alex",
               "mois_debut": "2026-12", "commentaire": "canapé", "session_id": SESSION}
    payload.update(body)
    return client.post("/api/v1/budget/installments", json=payload)


def split(**body):
    payload = {"mot_cle": "amazon", "montant_total": 60, "date": "2026-11-24", "session_id": SESSION,
               "parts": [{"categorie": "Course", "montant": 45}, {"categorie": "Chats", "montant": 15}]}
    payload.update(body)
    return client.post("/api/v1/budget/split-expenses", json=payload)


def test_installment_is_written_and_logged_as_an_undoable_recent_action(sport):
    sheet = install()

    res = installment()

    assert res.status_code == 201, res.text
    assert res.json()["message"] == "Échéancier créé : ikea, 400 € en 4 fois"
    [row] = rows(sheet, "Échéanciers")
    assert row[:5] == ["ikea", 400, 4, 0, 100] and row[6] == "Loisir Alex" and row[7] == "canapé"
    recent = client.get("/api/v1/home/recent-actions", params={"session_id": SESSION}).json()["items"][0]
    assert recent["id"] == res.json()["action_id"] and recent["undoable"] is True

    undo = client.post(f"/api/v1/home/recent-actions/{res.json()['action_id']}/undo", params={"session_id": SESSION})

    assert undo.status_code == 200, undo.text
    assert rows(sheet, "Échéanciers") == []


def test_installment_without_start_month_starts_this_month():
    sheet = install()
    assert installment(mois_debut=None, commentaire="").status_code == 201
    assert len(rows(sheet, "Échéanciers")) == 1


def test_installment_needs_two_payments_and_a_valid_month_and_category():
    sheet = install()
    assert installment(nb_echeances=1).status_code == 422
    assert installment(mois_debut="2026-13").status_code == 422
    unknown = installment(categorie="Jardin")
    assert unknown.status_code == 422 and "Jardin" in unknown.json()["detail"]
    assert all(not ws.writes for ws in sheet.worksheets())


def test_split_expense_is_declared_and_undone_from_recent_actions(sport):
    sheet = install()

    res = split()

    assert res.status_code == 201, res.text
    assert res.json()["message"] == "Dépense multiple pré-déclarée : amazon, 60 €"
    [row] = rows(sheet, "Dépenses Multiples")
    assert row[1:4] == ["amazon", 60, "A traiter"]

    undo = client.post(f"/api/v1/home/recent-actions/{res.json()['action_id']}/undo", params={"session_id": SESSION})

    assert undo.status_code == 200, undo.text
    assert rows(sheet, "Dépenses Multiples") == []


def test_split_parts_must_add_up_to_the_total_and_use_known_categories():
    sheet = install()

    wrong_sum = split(montant_total=70)
    unknown = split(parts=[{"categorie": "Jardin", "montant": 60}])

    assert wrong_sum.status_code == 422 and "70" in wrong_sum.json()["detail"]
    assert unknown.status_code == 422 and "Jardin" in unknown.json()["detail"]
    assert split(parts=[]).status_code == 422
    assert all(not ws.writes for ws in sheet.worksheets())


def test_plan_forms_answer_503_when_the_sheet_is_unavailable():
    set_budget_connector(None, error="SPREADSHEET_BUDGET_ID n'est pas renseigné")
    assert installment().status_code == 503
    assert split().status_code == 503
