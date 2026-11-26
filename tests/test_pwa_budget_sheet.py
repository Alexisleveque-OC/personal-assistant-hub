"""Phase 10, étape 7a : feuille « Budget » de la PWA (menu, balisage, client API, vue sans injection HTML).

Groupes repliés à l'ouverture (décision utilisateur du 25/11), non mémorisés. Étape 7b : bouton « + » de l'en-tête
qui ouvre le formulaire Dépense / Revenu en feuille empilée (décisions du 26/11).
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
    assert 'import { initBudget, loadBudget } from "./views/budget_view.js";' in shell
    assert "initBudget(manager);" in shell
    assert re.search(r'section === "budget"\) \{\s*loadBudget\(\);', shell)


def test_budget_header_opens_a_stacked_entry_form():
    html = rendered_html()
    sheet = section(html, "view-budget")
    assert 'id="btn-budget-add"' in sheet and 'aria-label="Noter une dépense ou un revenu"' in sheet
    form = section(html, "view-budget-form")
    assert 'class="sheet sheet--stacked" id="view-budget-form"' in html
    assert "<select" not in form  # liste trop longue (retour du 26/11) : champ texte avec suggestions
    for needle in ('id="budget-form"', 'data-type="depense"', 'data-type="revenu"', 'id="budget-form-montant"',
                   'inputmode="decimal"', 'id="budget-form-categorie"', 'role="combobox"',
                   'aria-controls="budget-form-suggestions"', 'id="budget-form-suggestions" role="listbox"',
                   'id="budget-form-libelle"',
                   'id="budget-form-date"', 'id="budget-form-swile"', 'id="budget-form-remboursement"',
                   'id="budget-form-expense-options"', 'id="budget-form-errors"', 'form="budget-form"'):
        assert needle in form, needle


def test_form_view_saves_then_offers_undo_without_html_injection():
    view = static_source("js/views/budget_form_view.js")
    for needle in ("budgetFormToPayload(", "categoryChoices(", "addBudgetEntry", "addBudgetInstallment",
                   "addBudgetSplitExpense", "undoRecentAction(", "getActiveSessionId()", '"Annuler"', "action_id",
                   "bindCombo(", "fillRemainder(", "splitRemainder("):
        assert needle in view, needle
    combo = static_source("js/views/budget_combo.js")
    for needle in ("matchCategories(", "aria-expanded", '"option"', '"listbox"', "is-searching"):
        assert needle in combo, needle
    for source in (view, combo):
        assert "innerHTML" not in source and "alert(" not in source


def test_form_has_four_tabs_and_the_installment_and_split_fields():
    """Étape 7c (décisions du 26/11) : 4 onglets dans la même feuille ; parts avec « reste à répartir »."""
    form = section(rendered_html(), "view-budget-form")
    for kind, label in (("depense", "Dépense"), ("revenu", "Revenu"), ("echeancier", "Échéancier"),
                        ("multiple", "Multiple")):
        assert f'data-type="{kind}" aria-pressed="{str(kind == "depense").lower()}">{label}</button>' in form
    for needle in ('id="budget-form-nom"', 'id="budget-form-nb-echeances"', 'type="month" id="budget-form-mois-debut"',
                   'id="budget-form-commentaire"', 'id="budget-form-mot-cle"', 'id="budget-form-parts"',
                   'id="btn-budget-add-part"', 'id="budget-form-remainder" aria-live="polite"',
                   'data-types="depense revenu echeancier"', 'data-types="multiple"'):
        assert needle in form, needle
    assert "initBudgetForm(" in static_source("js/views/budget_view.js")
