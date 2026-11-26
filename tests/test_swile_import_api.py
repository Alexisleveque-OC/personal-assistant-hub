"""Phase 10, étape 8 (3/4) : POST /api/v1/budget/swile/import, écriture des lignes relues (faux classeur).

Décisions utilisateur du 26/11 : dépenses → `Swile` (Commentaires « Swile : <marchand> »), crédits → `Revenus`,
solde → « Reste Swile » (Prévu du mois actif) en remplaçant la valeur ; tout l'import est une seule action de
« Dernières actions », annulée d'un coup (refus si une ligne a changé depuis), solde remis à l'ancienne valeur.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.connectors.sheets.budget_connector import BudgetConnector, BudgetConnectorError
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.dependencies import set_budget_connector, set_sport_connector
from app.main import app
from tests.budget_fakes import serial
from tests.test_swile_review_api import STATE, set_reste_swile
from tests.test_swile_review_api import reste_swile_value as reste_swile

client = TestClient(app)
TODAY = date(2026, 11, 26)
SESSION = "pwa-swile"


@pytest.fixture(autouse=True)
def sport(isolate_sqlite_database):
    """Le service d'annulation exige le carnet Sport (toujours présent en production)."""
    set_sport_connector(SqlSportConnector(db_manager=isolate_sqlite_database))
    yield
    set_sport_connector(None)


def install(reste_swile=None):
    from tests.budget_fakes import build_budget_spreadsheet
    sheet = build_budget_spreadsheet(STATE)
    if reste_swile is not None:
        set_reste_swile(sheet, reste_swile)
    set_budget_connector(BudgetConnector(sheet, today=lambda: TODAY))
    return sheet


def rows(sheet, title):
    return [r[:5] for r in sheet.worksheet(title).get_all_values(value_render_option="UNFORMATTED_VALUE")[1:]
            if any(str(c).strip() for c in r)]


def expense(marchand="Intermarche", montant=12.81, day="2026-11-25", categorie="Course"):
    return {"type": "depense", "date": day, "montant": montant, "marchand": marchand, "categorie": categorie}


CREDIT = {"type": "credit", "date": "2026-11-06", "montant": 242.0, "marchand": "Crédit titres-resto",
          "categorie": "Ticket resto"}


def post(lignes, solde=None):
    return client.post("/api/v1/budget/swile/import", json={"lignes": lignes, "solde": solde, "session_id": SESSION})


def recent():
    return client.get("/api/v1/home/recent-actions", params={"session_id": SESSION}).json()["items"][0]


def test_lines_credit_and_balance_are_written_and_logged_as_one_undoable_action():
    sheet = install(reste_swile=80.0)

    res = post([expense(), expense("Maryann", 6.9, "2026-11-23", "Restaurant"), CREDIT], solde=95.64)

    assert res.status_code == 201, res.text
    assert rows(sheet, "Swile") == [
        [serial(date(2026, 11, 25)), 12.81, "Course", "Swile : Intermarche"],
        [serial(date(2026, 11, 23)), 6.9, "Restaurant", "Swile : Maryann"],
    ]
    assert rows(sheet, "Revenus") == [[serial(date(2026, 11, 6)), 242.0, "Ticket resto", "", "Swile : Crédit titres-resto"]]
    assert reste_swile(sheet) == 95.64
    message = "Import Swile : 3 lignes, solde 95,64 €"
    assert res.json()["message"] == message
    item = recent()
    assert item["id"] == res.json()["action_id"] and item["label"] == message and item["undoable"] is True


def test_each_sheet_is_written_in_one_call_whatever_the_number_of_lines():
    sheet = install()

    res = post([expense(montant=float(n + 1), day=f"2026-11-{n + 1:02d}") for n in range(12)])

    assert res.status_code == 201, res.text
    assert len(sheet.worksheet("Swile").writes) == 1  # quota Sheets : une écriture, pas une par ligne
    assert len(rows(sheet, "Swile")) == 12


def test_undo_removes_every_line_and_restores_the_previous_balance():
    sheet = install(reste_swile=80.0)
    action_id = post([expense(), expense(), CREDIT], solde=95.64).json()["action_id"]

    res = client.post(f"/api/v1/home/recent-actions/{action_id}/undo", params={"session_id": SESSION})

    assert res.status_code == 200, res.text
    assert rows(sheet, "Swile") == [] and rows(sheet, "Revenus") == []
    assert reste_swile(sheet) == 80.0


def test_undo_empties_a_balance_that_was_empty():
    sheet = install()
    action_id = post([], solde=95.64).json()["action_id"]

    client.post(f"/api/v1/home/recent-actions/{action_id}/undo", params={"session_id": SESSION})

    assert reste_swile(sheet) == ""


def test_undo_is_refused_as_a_whole_when_a_line_changed_since():
    sheet = install(reste_swile=80.0)
    action_id = post([expense(), CREDIT], solde=95.64).json()["action_id"]
    sheet.worksheet("Swile").rows[1][2] = "Restaurant"  # recatégorisée à la main dans le classeur

    res = client.post(f"/api/v1/home/recent-actions/{action_id}/undo", params={"session_id": SESSION})

    assert res.status_code in (400, 409, 422), res.text
    assert "Swile : Intermarche" in res.text
    assert len(rows(sheet, "Revenus")) == 1 and reste_swile(sheet) == 95.64  # rien n'a été annulé


@pytest.mark.parametrize("ligne, wanted", [
    (expense(categorie="Loisir"), "groupe"),
    (expense(categorie="Inconnue"), "Inconnue"),
    (expense(categorie="Ticket resto"), "Ticket resto"),  # type de revenu : pas une dépense
    ({**CREDIT, "categorie": "Course"}, "Course"),  # catégorie de dépense : pas un revenu
])
def test_a_wrong_category_refuses_the_whole_import(ligne, wanted):
    sheet = install()

    res = post([expense(), ligne], solde=95.64)

    assert res.status_code == 422
    assert wanted in res.json()["detail"]
    assert rows(sheet, "Swile") == [] and rows(sheet, "Revenus") == [] and reste_swile(sheet) == ""


def test_categories_are_written_with_their_exact_name():
    sheet = install()

    post([expense(categorie="course"), expense(montant=5.0, categorie="cadeaux elias")])

    assert [r[2] for r in rows(sheet, "Swile")] == ["Course", "Cadeaux Elias "]


def test_nothing_to_import_is_refused():
    install()
    res = post([], solde=None)
    assert res.status_code == 422


def test_written_lines_are_removed_when_a_later_write_fails():
    sheet = install()
    revenus = sheet.worksheet("Revenus")

    def refused(*_, **__):
        raise BudgetConnectorError("Google a refusé l'écriture (quota)")

    revenus.update = refused
    res = post([expense(), CREDIT])

    assert res.status_code == 502
    assert "quota" in res.json()["detail"]
    assert rows(sheet, "Swile") == []


def test_a_failed_roll_back_lists_the_lines_left_in_the_sheet():
    sheet = install()

    def refused(*_, **__):
        raise BudgetConnectorError("Google a refusé l'écriture (quota)")

    sheet.worksheet("Revenus").update = refused
    sheet.worksheet("Swile").delete_rows = refused
    res = post([expense(), CREDIT])

    assert res.status_code == 502
    detail = res.json()["detail"]
    assert "Swile : Intermarche 12.81 € le 25/11" in detail and "À supprimer à la main" in detail
