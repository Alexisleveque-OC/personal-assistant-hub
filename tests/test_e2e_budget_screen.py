"""Test E2E de l'écran Budget (Phase 10, étape 7a) : faux classeur → BudgetConnector → GET /api/v1/budget/overview
→ feuille Budget dans un vrai Chromium (Playwright).

Le serveur E2E n'a aucun accès Google : la réponse de l'endpoint est calculée par l'application elle-même (TestClient)
sur le faux classeur, puis servie au navigateur à la place de l'appel réseau. Aucune donnée réelle, lecture seule.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.connectors.sheets.budget_connector import BudgetConnector
from app.core.dependencies import set_budget_connector
from app.main import app
from tests.budget_fakes import BudgetSheetState, GestionLine, build_budget_spreadsheet
from tests.test_e2e_navigation import base_url, browser, e2e_server, page  # noqa: F401 (fixtures)

NOV, OCT = (2026, 11), (2026, 10)


@pytest.fixture
def overview_json():
    state = BudgetSheetState(
        groups=(
            ("Courants", (GestionLine("Course", 923.15, planned={NOV: 1000}, spent={NOV: 76.02}),
                          GestionLine("Restaurant", -100.69, planned={NOV: 35}, spent={NOV: 49}))),
            ("Revenus", (GestionLine("Salaire Amélie", -1886.74, planned={NOV: 1947.79}, spent={NOV: 1973.55}),)),
        ),
        monthly_totals={OCT: (4839.65, 4468.81, -370.84), NOV: (203.2, 2215.55, 2012.35)},
    )
    sheet = build_budget_spreadsheet(state)
    set_budget_connector(BudgetConnector(sheet, today=lambda: date(2026, 11, 25)))
    res = TestClient(app).get("/api/v1/budget/overview")
    assert res.status_code == 200, res.text
    assert all(not ws.writes for ws in sheet.worksheets())  # lecture seule
    return res.text


def test_budget_sheet_shows_chart_and_collapsed_groups_then_expands_one(page, overview_json):
    page.route("**/api/v1/budget/overview", lambda route: route.fulfill(
        status=200, content_type="application/json", body=overview_json))
    page.click("#btn-open-drawer")
    page.click(".drawer__item[data-section='budget']")
    page.wait_for_selector("#view-budget[aria-hidden='false'] .budget-summary")

    assert page.text_content("#budget-month") == "novembre 2026"
    assert page.text_content(".budget-saved .budget-amount").replace(" ", " ") == "2 012,35 €"
    assert page.locator(".budget-bars .bars__col").count() == 3  # septembre à novembre (mois actif)
    assert "novembre : dépenses 203,20" in page.text_content(".budget-chart__caption")

    heads = page.locator(".budget-group__head")
    assert heads.count() == 2
    assert [heads.nth(i).get_attribute("aria-expanded") for i in range(2)] == ["false", "false"]
    assert not page.is_visible(".budget-cat")

    heads.nth(0).click()
    assert heads.nth(0).get_attribute("aria-expanded") == "true"
    restaurant = page.locator(".budget-group--expense .budget-cat").nth(1)
    assert "budget-amount--danger" in restaurant.locator(".budget-amount").get_attribute("class")
    assert "dépensé 49" in restaurant.text_content()
    assert "progress--warn" in restaurant.locator(".progress").get_attribute("class")

    heads.nth(1).click()
    salary = page.locator(".budget-group--income .budget-cat").first
    assert "reçu 1" in salary.text_content() and "prévu 1" in salary.text_content()
    assert "budget-amount--danger" not in salary.locator(".budget-amount").get_attribute("class")


def test_unavailable_sheet_shows_the_server_reason(page):
    page.click("#btn-open-drawer")
    page.click(".drawer__item[data-section='budget']")
    page.wait_for_selector("#budget-container .shopping-note--error")
    assert "Classeur Budget indisponible" in page.text_content("#budget-container")
