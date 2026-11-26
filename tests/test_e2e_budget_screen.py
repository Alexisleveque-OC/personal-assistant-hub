"""Test E2E de l'écran Budget (Phase 10, étapes 7a et 7b) : faux classeur → BudgetConnector → API → feuille Budget et
formulaire Dépense / Revenu dans un vrai Chromium (Playwright).

Le serveur E2E n'a aucun accès Google : les requêtes Budget du navigateur sont rejouées sur l'application elle-même
(TestClient) avec le faux classeur, et leur réponse lui est servie à la place de l'appel réseau. Aucune donnée réelle.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.connectors.sheets.budget_connector import BudgetConnector
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.dependencies import set_budget_connector, set_sport_connector
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
    assert heads.count() == 1  # pas de groupe Revenus (déjà dans le graphique)
    assert heads.nth(0).get_attribute("aria-expanded") == "false"
    assert not page.is_visible(".budget-cat")

    heads.nth(0).click()
    assert heads.nth(0).get_attribute("aria-expanded") == "true"
    restaurant = page.locator(".budget-cat").nth(1)
    assert "budget-amount--danger" in restaurant.locator(".budget-amount").get_attribute("class")
    assert "dépensé 49" in restaurant.text_content()
    assert "progress--warn" in restaurant.locator(".progress").get_attribute("class")
    assert "Salaire" not in page.text_content("#budget-container")


def test_unavailable_sheet_shows_the_server_reason(page):
    page.click("#btn-open-drawer")
    page.click(".drawer__item[data-section='budget']")
    page.wait_for_selector("#budget-container .shopping-note--error")
    assert "Classeur Budget indisponible" in page.text_content("#budget-container")


def _replay(client, sheet_calls):
    """Rejoue la requête du navigateur sur l'application (faux classeur) et lui sert la vraie réponse."""
    def handler(route):
        request = route.request
        path = request.url.split("://", 1)[1].split("/", 1)[1]
        sheet_calls.append((request.method, path.split("?")[0]))
        res = client.request(request.method, "/" + path, content=request.post_data,
                             headers={"Content-Type": "application/json"})
        route.fulfill(status=res.status_code, content_type="application/json", body=res.text)
    return handler


def test_entry_form_writes_an_expense_then_the_toast_undoes_it(page, isolate_sqlite_database):
    state = BudgetSheetState(groups=(
        ("Courants", (GestionLine("Course", 923.15, planned={NOV: 1000}, spent={NOV: 76.02}),)),
        ("Revenus", (GestionLine("CAF", 0, planned={NOV: 151.05}),)),
    ))
    sheet = build_budget_spreadsheet(state)
    set_budget_connector(BudgetConnector(sheet, today=lambda: date(2026, 11, 25)))
    set_sport_connector(SqlSportConnector(db_manager=isolate_sqlite_database))  # exigé par le service d'annulation
    calls = []
    handler = _replay(TestClient(app), calls)
    page.route("**/api/v1/budget/**", handler)
    page.route("**/api/v1/home/recent-actions/*/undo*", handler)
    debit = lambda: [r for r in sheet.worksheet("Débit").get_all_values(value_render_option="UNFORMATTED_VALUE")[1:]
                     if any(str(c).strip() for c in r)]
    try:
        page.click("#btn-open-drawer")
        page.click(".drawer__item[data-section='budget']")
        page.wait_for_selector("#view-budget[aria-hidden='false'] .budget-summary")
        page.click("#btn-budget-add")
        page.wait_for_selector("#view-budget-form[aria-hidden='false']")

        page.click("#budget-form-type [data-type='revenu']")
        assert page.text_content("#budget-form-categorie-label") == "Type de revenu"
        assert page.is_hidden("#budget-form-expense-options")
        page.fill("#budget-form-categorie", "ca")
        assert page.locator("#budget-form-suggestions [role='option']").all_text_contents() == ["CAFRevenus"]
        page.click("#budget-form-type [data-type='depense']")
        assert page.input_value("#budget-form-categorie") == ""  # Dépense et Revenu n'ont aucune catégorie commune

        page.click("#view-budget-form [type='submit']")
        assert "Montant invalide" in page.text_content("#budget-form-errors")
        assert ("POST", "api/v1/budget/entries") not in calls

        page.fill("#budget-form-montant", "12,50")
        page.fill("#budget-form-categorie", "cour")
        assert page.get_attribute("#budget-form-categorie", "aria-expanded") == "true"
        # Le clavier du téléphone couvre le bas de l'écran : le champ remonte sous l'en-tête de la feuille.
        gap = page.evaluate("""() => document.querySelector('.budget-combo').getBoundingClientRect().top
            - document.querySelector('#view-budget-form .sheet__body').getBoundingClientRect().top""")
        assert 0 <= gap <= 16, gap
        page.click("#budget-form-suggestions [role='option']:has-text('Course')")
        assert page.input_value("#budget-form-categorie") == "Course"
        assert page.is_hidden("#budget-form-suggestions")
        page.fill("#budget-form-libelle", "pain")
        page.click("#view-budget-form [type='submit']")
        page.wait_for_selector("#view-budget-form[aria-hidden='true']", state="attached")
        toast = page.locator(".notice--success").filter(has_text="Dépense enregistrée : 12,5 € en Course")
        toast.wait_for()
        assert len(debit()) == 1 and debit()[0][4] == "Otis : pain"

        toast.locator(".btn-undo-action").click()
        page.locator(".notice--success").filter(has_text="C'est annulé").wait_for()
        assert debit() == []
        assert len([c for c in calls if c[0] == "GET"]) >= 3  # écran rechargé après la saisie et l'annulation
        assert not page.script_errors
    finally:
        set_sport_connector(None)


def _open_form(page):
    page.click("#btn-open-drawer")
    page.click(".drawer__item[data-section='budget']")
    page.wait_for_selector("#view-budget[aria-hidden='false'] .budget-summary")
    page.click("#btn-budget-add")
    page.wait_for_selector("#view-budget-form[aria-hidden='false']")


def _rows(sheet, title):
    values = sheet.worksheet(title).get_all_values(value_render_option="UNFORMATTED_VALUE")[1:]
    return [r for r in values if any(str(c).strip() for c in r)]


@pytest.fixture
def default_sheet(page):
    sheet = build_budget_spreadsheet(BudgetSheetState())
    set_budget_connector(BudgetConnector(sheet, today=lambda: date(2026, 11, 25)))
    calls = []
    page.route("**/api/v1/budget/**", _replay(TestClient(app), calls))
    return sheet


def test_split_form_fills_the_rest_into_a_part_then_declares_it(page, default_sheet):
    _open_form(page)
    page.click("#budget-form-type [data-type='multiple']")
    assert page.text_content("#budget-form-montant-label") == "Montant total débité (€)"
    assert page.is_hidden("#budget-form-libelle") and page.is_visible("#budget-form-mot-cle")

    page.fill("#budget-form-montant", "60")
    page.fill("#budget-form-mot-cle", "amazon")
    page.fill("#budget-part-0-categorie", "cour")
    page.click("#budget-part-0-suggestions [role='option']:has-text('Course')")
    page.fill("#budget-part-0-montant", "45")
    assert page.text_content("#budget-form-remainder").replace(" ", " ") == "Reste à répartir : 15 €"
    page.fill("#budget-part-1-categorie", "chat")
    page.click("#budget-part-1-suggestions [role='option']:has-text('Chats')")
    page.click("#budget-form-parts .budget-part:nth-child(2) .budget-part__rest")
    assert page.input_value("#budget-part-1-montant") == "15,00"
    assert page.text_content("#budget-form-remainder").replace(" ", " ") == "Reste à répartir : 0 €"

    page.click("#view-budget-form [type='submit']")
    page.locator(".notice--success").filter(has_text="Dépense multiple pré-déclarée : amazon, 60 €").wait_for()
    [row] = _rows(default_sheet, "Dépenses Multiples")
    assert row[1:4] == ["amazon", 60, "A traiter"]
    assert not page.script_errors


def test_installment_form_creates_an_installment(page, default_sheet):
    _open_form(page)
    page.click("#budget-form-type [data-type='echeancier']")
    assert page.is_visible("#budget-form-nom") and page.is_hidden("#budget-form-libelle")
    page.fill("#budget-form-montant", "400")
    page.fill("#budget-form-nom", "ikea")
    page.fill("#budget-form-nb-echeances", "4")
    page.fill("#budget-form-categorie", "loisir a")
    page.click("#budget-form-suggestions [role='option']:has-text('Loisir Alex')")
    page.fill("#budget-form-mois-debut", "2026-12")

    page.click("#view-budget-form [type='submit']")
    page.locator(".notice--success").filter(has_text="Échéancier créé : ikea, 400 € en 4 fois").wait_for()
    [row] = _rows(default_sheet, "Échéanciers")
    assert row[:5] == ["ikea", 400, 4, 0, 100] and row[6] == "Loisir Alex"
    assert not page.script_errors
