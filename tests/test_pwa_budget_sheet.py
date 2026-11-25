"""Phase 10, étape 7a : feuille « Budget » de la PWA (menu, balisage, client API, vue sans injection HTML).

Lecture seule : la saisie passe par la barre d'Otis (formulaires en 7b / 7c). Groupes repliés à l'ouverture
(décision utilisateur du 25/11), non mémorisés.
"""
import re

from tests.js_helpers import rendered_html, section, static_source


def test_menu_has_a_budget_entry_and_a_budget_sheet():
    html = rendered_html()
    assert re.search(r'class="drawer__item" data-section="budget">.*?<span class="drawer__label">Budget</span>', html)
    sheet = section(html, "view-budget")
    assert 'aria-labelledby="view-budget-title"' in html
    assert 'id="view-budget-title">Budget <small id="budget-month"></small>' in sheet
    assert 'id="budget-container"' in sheet
    assert 'class="composer-slot"' in sheet  # « 12 € de courses » se dicte depuis la feuille


def test_api_client_fetches_the_overview_with_an_explicit_error():
    source = static_source("js/api/budget.js")
    assert 'fetch("/api/v1/budget/overview"' in source and "getAuthHeaders()" in source
    assert "detail" in source and "throw new Error" in source
    assert 'export * from "./api/budget.js";' in static_source("js/api.js")


def test_view_renders_the_model_collapsed_and_without_html_injection():
    view = static_source("js/views/budget_view.js")
    for needle in ("budgetSheet(", "fetchBudgetOverview(", "aria-expanded", '"false"', "bars__col", "progress",
                   "role", "progressbar"):
        assert needle in view, needle
    assert "innerHTML" not in view and "alert(" not in view


def test_shell_loads_the_budget_sheet_on_opening():
    shell = static_source("js/app_shell.js")
    assert 'import { loadBudget } from "./views/budget_view.js";' in shell
    assert re.search(r'section === "budget"\) \{\s*loadBudget\(\);', shell)
