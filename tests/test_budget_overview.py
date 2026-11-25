"""Phase 10, étape 7a : vue d'ensemble de l'écran Budget (faux classeur hors-ligne, aucun appel à Google).

Groupes et catégories de `Gestion` (reste total en colonne B ; budget du mois = Prévu + Equilibrage du mois actif),
dépensé du mois = ligne de la catégorie dans `Total dépenses`, série Dépenses / Revenus de l'année du mois actif
et épargné du mois actif (lignes 5-7 de `Total dépenses`). Catégories terminées masquées.
"""
from datetime import date

import pytest

from app.connectors.sheets.budget_connector import (
    BudgetCategoryNotFoundError,
    BudgetConnector,
    BudgetConnectorError,
    BudgetHeaderError,
)
from app.connectors.sheets.budget_models import BudgetMonth
from tests.budget_fakes import DEFAULT_CATEGORIES, BudgetSheetState, GestionLine, build_budget_spreadsheet

TODAY = date(2026, 11, 25)
NOV, OCT, SEP, DEC = (2026, 11), (2026, 10), (2026, 9), (2026, 12)


def overview(state: BudgetSheetState = None):
    sheet = build_budget_spreadsheet(state or BudgetSheetState())
    return BudgetConnector(sheet, today=lambda: TODAY).get_overview()


def by_name(result):
    return {c.name: c for g in result.groups for c in g.categories}


def test_active_month_saved_amount_and_series_of_the_year_up_to_the_active_month() -> None:
    state = BudgetSheetState(
        months=((2025, 12), SEP, OCT, NOV, DEC),
        monthly_totals={(2025, 12): (9.0, 9.0, 9.0), SEP: (4650.96, 4504.6, -146.36), OCT: (4839.65, 4468.81, -370.84),
                        NOV: (203.2, 2215.55, 2012.35)},
    )
    result = overview(state)
    assert result.active_month == BudgetMonth(year=2026, month=11)
    assert result.saved == 2012.35
    assert [(p.month.month, p.expenses, p.income) for p in result.series] == [
        (9, 4650.96, 4504.6), (10, 4839.65, 4468.81), (11, 203.2, 2215.55),
    ]


def test_groups_follow_gestion_order_and_revenus_is_an_income_group() -> None:
    result = overview()
    assert [(g.name, g.kind) for g in result.groups] == [
        ("Courants", "expense"), ("Loisir", "expense"), ("Fixes", "expense"), ("Epargne", "expense"),
        ("Revenus", "income"),
    ]
    assert [c.name for c in result.groups[0].categories] == ["Course", "Restaurant", "Chats"]


def test_category_has_total_remaining_month_spent_and_budget_planned_plus_balancing() -> None:
    state = BudgetSheetState(groups=(
        ("Courants", (
            GestionLine("Course", 923.154, planned={NOV: 1000}, balancing={NOV: 629.39}, spent={NOV: 76.0199999}),
            GestionLine("Restaurant", -100.69, planned={NOV: 35}, spent={NOV: 49}),
        )),
    ))
    cats = by_name(overview(state))
    assert (cats["Course"].total_remaining, cats["Course"].month_spent, cats["Course"].month_budget) == (
        923.15, 76.02, 1629.39)
    assert (cats["Restaurant"].total_remaining, cats["Restaurant"].month_spent, cats["Restaurant"].month_budget) == (
        -100.69, 49.0, 35.0)


def test_blank_planned_balancing_or_spent_count_as_zero() -> None:
    state = BudgetSheetState(groups=(
        ("A rembourser", (GestionLine("Déménagement", -1856.51, planned={NOV: ""}, spent={NOV: ""}),)),
    ))
    cat = by_name(overview(state))["Déménagement"]
    assert (cat.month_spent, cat.month_budget) == (0.0, 0.0)


def test_group_total_is_the_sum_of_all_its_categories() -> None:
    result = overview()
    courants = result.groups[0]
    assert courants.total_remaining == round(412.5 - 35.2 + 80.0, 2)


def test_ended_categories_are_hidden_but_still_count_in_the_group_total() -> None:
    # « Vacances 2025 » est terminée (31/12/2025) dans Catégories ; le groupe « Vieux » n'a plus rien à montrer.
    state = BudgetSheetState(
        groups=(("Divers", (GestionLine("Vacances 2025", -12.5), GestionLine("Vacances", 40.0))),
                ("Vieux", (GestionLine("Vieille cat", 0.0),))),
        categories=DEFAULT_CATEGORIES + (("Vacances", date(2024, 1, 1), None),
                                         ("Vieille cat", date(2024, 1, 1), date(2025, 6, 30))),
    )
    result = overview(state)
    assert [(g.name, [c.name for c in g.categories], g.total_remaining) for g in result.groups] == [
        ("Divers", ["Vacances"], 27.5),
    ]


def test_category_absent_from_categories_tab_is_kept() -> None:
    state = BudgetSheetState(groups=(("Divers", (GestionLine("Sans fiche", 5.0),)),))
    assert list(by_name(overview(state))) == ["Sans fiche"]


def test_category_named_like_its_group_reads_its_own_line_of_total_depenses() -> None:
    state = BudgetSheetState(groups=(
        ("Epargne", (GestionLine("épargne Candice", 1675.0, spent={NOV: 25}),
                     GestionLine("Epargne", 0.0, spent={NOV: 7}))),
    ))
    assert by_name(overview(state))["Epargne"].month_spent == 7.0


def test_category_missing_from_total_depenses_is_explicit() -> None:
    state = BudgetSheetState()
    sheet = build_budget_spreadsheet(state)
    total = sheet.worksheet("Total dépenses")
    total.rows = [row for row in total.rows if not row or row[0] != "Chats"]
    with pytest.raises(BudgetCategoryNotFoundError, match=r"« Chats ».*Total dépenses.*Course"):
        BudgetConnector(sheet, today=lambda: TODAY).get_overview()


def test_total_lines_drift_is_explicit() -> None:
    state = BudgetSheetState(total_labels=("Total dépense", "Revenus totaux", "Total épargné"))
    with pytest.raises(BudgetHeaderError, match=r"Total revenus.*ligne 6.*Revenus totaux"):
        overview(state)


def test_text_in_a_planned_cell_names_the_cell() -> None:
    state = BudgetSheetState(groups=(("Courants", (GestionLine("Course", 1.0, planned={NOV: "beaucoup"}),)),))
    with pytest.raises(BudgetConnectorError, match=r"Course.*Prévu.*novembre 2026"):
        overview(state)


def test_overview_is_served_from_the_cache() -> None:
    sheet = build_budget_spreadsheet(BudgetSheetState())
    connector = BudgetConnector(sheet, today=lambda: TODAY)
    connector.get_overview()
    reads = {ws.title: ws.reads for ws in sheet.worksheets()}
    connector.get_overview()
    assert {ws.title: ws.reads for ws in sheet.worksheets()} == reads
