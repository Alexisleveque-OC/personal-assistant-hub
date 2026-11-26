"""Phase 10, étape 7b : POST /api/v1/budget/entries, formulaire Dépense / Revenu de l'écran Budget (faux classeur).

Décisions utilisateur du 26/11 : mêmes écritures que la voix (intitulé « Otis : <libellé> », libellé obligatoire),
saisie inscrite au journal → visible dans « Dernières actions » et annulable (refus si la ligne a changé depuis).
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.connectors.sheets.budget_connector import BudgetConnector
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.clock import paris_today
from app.core.dependencies import set_budget_connector, set_sport_connector
from app.main import app
from tests.budget_fakes import BudgetSheetState, build_budget_spreadsheet

client = TestClient(app)
TODAY = date(2026, 11, 25)
SESSION = "pwa-1"


def install(state: BudgetSheetState = None):
    sheet = build_budget_spreadsheet(state or BudgetSheetState())
    set_budget_connector(BudgetConnector(sheet, today=lambda: TODAY))
    return sheet


def rows(sheet, title):
    return [r for r in sheet.worksheet(title).get_all_values(value_render_option="UNFORMATTED_VALUE")[1:] if any(str(c).strip() for c in r)]


def post(**body):
    payload = {"type": "depense", "montant": 12.5, "categorie": "Course", "libelle": "pain", "session_id": SESSION}
    payload.update(body)
    return client.post("/api/v1/budget/entries", json=payload)


def test_expense_is_written_to_debit_and_logged_as_an_undoable_recent_action():
    sheet = install()

    res = post(date="2026-11-24")

    assert res.status_code == 201, res.text
    body = res.json()
    assert body["message"] == "Dépense enregistrée : 12,5 € en Course"
    assert body["ligne"]["onglet"] == "Débit" and body["ligne"]["intitule"] == "Otis : pain"
    assert len(rows(sheet, "Débit")) == 1
    recent = client.get("/api/v1/home/recent-actions", params={"session_id": SESSION}).json()["items"][0]
    assert recent["id"] == body["action_id"]
    assert recent["label"] == "Dépense enregistrée : 12,5 € en Course" and recent["undoable"] is True


@pytest.fixture
def sport(isolate_sqlite_database):
    """Le service d'annulation exige le carnet Sport (toujours présent en production)."""
    set_sport_connector(SqlSportConnector(db_manager=isolate_sqlite_database))
    yield
    set_sport_connector(None)


def test_form_entry_is_undone_from_recent_actions(sport):
    sheet = install()
    action_id = post().json()["action_id"]

    res = client.post(f"/api/v1/home/recent-actions/{action_id}/undo", params={"session_id": SESSION})

    assert res.status_code == 200, res.text
    assert rows(sheet, "Débit") == []


def test_refund_is_a_negative_line_and_swile_goes_to_the_swile_sheet():
    sheet = install()

    refund = post(remboursement=True, montant=20, categorie="Restaurant", libelle="trop perçu")
    swile = post(swile=True, montant=9.9, categorie="Restaurant", libelle="midi")

    assert refund.status_code == 201 and swile.status_code == 201
    assert refund.json()["message"] == "Remboursement enregistré : 20 € en Restaurant"
    assert refund.json()["ligne"]["montant"] == -20.0
    assert swile.json()["ligne"]["onglet"] == "Swile" and len(rows(sheet, "Swile")) == 1


def test_income_is_written_to_revenus_with_a_type_of_the_revenus_group():
    sheet = install()

    res = post(type="revenu", montant=151.05, categorie="CAF", libelle="CAF novembre")

    assert res.status_code == 201, res.text
    assert res.json()["message"] == "Revenu enregistré : 151,05 € en CAF"
    assert res.json()["ligne"]["date"] == paris_today().isoformat()  # date laissée vide = aujourd'hui
    assert len(rows(sheet, "Revenus")) == 1


def test_unknown_category_or_group_name_is_refused_without_writing():
    sheet = install()

    unknown = post(categorie="Jardin")
    group = post(categorie="Loisir")
    not_income = post(type="revenu", categorie="Course")

    assert [r.status_code for r in (unknown, group, not_income)] == [422, 422, 422]
    assert "Jardin" in unknown.json()["detail"]
    assert "Loisir Alex" in group.json()["detail"]
    assert "CAF" in not_income.json()["detail"]
    assert all(not ws.writes for ws in sheet.worksheets())


def test_income_cannot_be_a_refund_or_paid_in_swile():
    install()
    assert post(type="revenu", categorie="CAF", swile=True).status_code == 422
    assert post(type="revenu", categorie="CAF", remboursement=True).status_code == 422


def test_blank_label_or_non_positive_amount_is_refused():
    install()
    assert post(libelle="  ").status_code == 422
    assert post(montant=0).status_code == 422


def test_unavailable_sheet_answers_503():
    set_budget_connector(None, error="SPREADSHEET_BUDGET_ID n'est pas renseigné")
    res = post()
    assert res.status_code == 503
    assert "SPREADSHEET_BUDGET_ID n'est pas renseigné" in res.json()["detail"]
