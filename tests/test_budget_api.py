"""Phase 10, étape 7a : GET /api/v1/budget/overview, lecture seule pour l'écran Budget de la PWA (faux classeur)."""
from datetime import date

from fastapi.testclient import TestClient

from app.config import settings
from app.connectors.sheets.budget_connector import BudgetConnector
from app.core.dependencies import set_budget_connector
from app.main import app
from tests.budget_fakes import BudgetSheetState, GestionLine, build_budget_spreadsheet

client = TestClient(app)
NOV = (2026, 11)


def install(state: BudgetSheetState = None):
    sheet = build_budget_spreadsheet(state or BudgetSheetState())
    set_budget_connector(BudgetConnector(sheet, today=lambda: date(2026, 11, 25)))
    return sheet


def test_overview_returns_month_series_and_groups():
    install(BudgetSheetState(
        groups=(("Courants", (GestionLine("Course", 923.15, planned={NOV: 1000}, spent={NOV: 76.02}),)),
                ("Revenus", (GestionLine("CAF", -20.0, planned={NOV: 151.05}, spent={NOV: 240.45}),))),
        monthly_totals={NOV: (203.2, 2215.55, 2012.35)},
    ))

    res = client.get("/api/v1/budget/overview")

    assert res.status_code == 200
    body = res.json()
    assert body["active_month"] == {"year": 2026, "month": 11}
    assert body["saved"] == 2012.35
    assert body["series"][-1] == {"month": {"year": 2026, "month": 11}, "expenses": 203.2, "income": 2215.55}
    assert body["groups"] == [
        {"name": "Courants", "total_remaining": 923.15, "categories": [
            {"name": "Course", "total_remaining": 923.15, "month_spent": 76.02, "month_budget": 1000.0}]},
    ]  # Revenus : seulement dans le graphique


def test_overview_never_writes_to_the_sheet():
    sheet = install()
    client.get("/api/v1/budget/overview")
    assert all(not getattr(ws, "writes", []) for ws in sheet.worksheets())


def test_unavailable_sheet_answers_503_with_the_reason():
    set_budget_connector(None, error="SPREADSHEET_BUDGET_ID n'est pas renseigné")

    res = client.get("/api/v1/budget/overview")

    assert res.status_code == 503
    assert "SPREADSHEET_BUDGET_ID n'est pas renseigné" in res.json()["detail"]


def test_sheet_structure_error_answers_502_with_the_explicit_message():
    install(BudgetSheetState(total_labels=("Total dépense", "Revenus totaux", "Total épargné")))

    res = client.get("/api/v1/budget/overview")

    assert res.status_code == 502
    assert "« Total revenus » attendu en ligne 6" in res.json()["detail"]


def test_budget_api_requires_the_api_key(monkeypatch):
    install()
    monkeypatch.setattr(settings, "api_key", "secret")

    assert client.get("/api/v1/budget/overview").status_code == 401
    assert client.get("/api/v1/budget/overview", headers={"X-API-Key": "secret"}).status_code == 200

