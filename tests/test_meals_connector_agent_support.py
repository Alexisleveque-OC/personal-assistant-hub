"""Primitives du connecteur Repas & Courses nécessaires aux outils agent et à leur annulation exacte (Phase 6.8)."""
from datetime import date

import pytest

from app.connectors.sheets.meals_connector import MealsShoppingConnector
from app.connectors.sheets.models import WaitingListItem
from tests.meals_fakes import MealsSheetState, WeekItem, build_meals_spreadsheet, waiting_rows, week_rows

TODAY = date(2026, 10, 21)


@pytest.fixture
def sheet():
    return build_meals_spreadsheet(MealsSheetState(
        today=TODAY,
        waiting=[("Lait", True), ("Pain", False), ("Café", True)],
        week=[WeekItem("Quinoa", "Épicerie", checked=True), WeekItem("Courgette", "Fruits & Légumes")],
    ))


@pytest.fixture
def connector(sheet):
    return MealsShoppingConnector(spreadsheet=sheet)


def test_waiting_list_rows_include_bought_items_and_bypass_the_cache(connector, sheet):
    connector.get_shopping_list()  # met en cache la vue « non achetés »
    sheet.worksheet("Liste_Attente").append_row([False, "Beurre", "21/10/2026"])

    rows = connector.get_waiting_list_rows()

    assert [(r.item, r.is_bought, r.added_at) for r in rows] == [
        ("Lait", True, "21/10/2026"), ("Pain", False, "21/10/2026"), ("Café", True, "21/10/2026"), ("Beurre", False, "21/10/2026"),
    ]


def test_restore_waiting_items_appends_rows_with_their_state_and_invalidates_cache(connector, sheet):
    assert [it.item for it in connector.get_shopping_list()["waiting_list"]] == ["Pain"]

    connector.restore_waiting_items([
        WaitingListItem(item="Beurre", is_bought=False, added_at="19/10/2026"),
        WaitingListItem(item="Thé", is_bought=True, added_at="18/10/2026"),
    ])

    assert waiting_rows(sheet)[-2:] == [("Beurre", False), ("Thé", True)]
    assert sheet.worksheet("Liste_Attente").rows[-1][2] == "18/10/2026"
    assert [it.item for it in connector.get_shopping_list()["waiting_list"]] == ["Pain", "Beurre"]


def test_unmark_waiting_items_only_touches_the_named_checked_rows(connector, sheet):
    unmarked = connector.unmark_shopping_items_bought(["lait"])

    assert unmarked == ["Lait"]
    assert waiting_rows(sheet) == [("Lait", False), ("Pain", False), ("Café", True)]
    assert "Lait" in [it.item for it in connector.get_shopping_list()["waiting_list"]]


def test_unmark_current_week_items_only_touches_the_named_checked_items(connector, sheet):
    unmarked = connector.unmark_current_week_items_bought(["Quinoa", "Courgette"])

    assert unmarked == ["Quinoa"]  # la courgette n'était pas cochée
    assert week_rows(sheet) == [("Quinoa", False), ("Courgette", False)]


@pytest.mark.parametrize("query, candidate, expected", [
    ("lait", "Lait", True),
    ("des œufs", "Œufs", True),
    ("courgettes", "Courgette", True),
    ("créme fraiche", "Crème fraîche", True),
    ("lait d'avoine", "Lait", False),
    ("pain", "Pain de mie", False),
])
def test_item_name_matching_tolerates_articles_accents_and_plurals(connector, query, candidate, expected):
    assert connector.matches_item_name(query, candidate) is expected
