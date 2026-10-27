"""Apprentissage persistant du rayon d'un article dans l'onglet « Ingredients_Rayons » (Phase 6.8)."""
from datetime import date

import pytest

from app.connectors.sheets.meals_connector import MealsShoppingConnector
from tests.meals_fakes import MealsSheetState, build_meals_spreadsheet

TODAY = date(2026, 10, 21)


@pytest.fixture
def sheet():
    return build_meals_spreadsheet(MealsSheetState(today=TODAY))


@pytest.fixture
def connector(sheet):
    return MealsShoppingConnector(spreadsheet=sheet)


def _ingredient_rows(sheet):
    return [tuple(row) for row in sheet.worksheet("Ingredients_Rayons").get_all_values()[1:]]


def test_learned_rayon_is_appended_to_the_sheet_and_resolves_immediately(connector, sheet):
    assert connector.resolve_rayon("Papier cadeau")[1] is not None  # inconnu, catalogue mis en cache

    connector.learn_ingredient_rayon("Papier cadeau", "Entretien")

    assert _ingredient_rows(sheet)[-1] == ("Papier cadeau", "Entretien")
    assert connector.resolve_rayon("papier cadeau") == ("Entretien", None)


def test_ingredient_with_empty_rayon_is_known_and_shown_in_divers(connector, sheet):
    connector.learn_ingredient_rayon("Bougies", "")

    assert _ingredient_rows(sheet)[-1] == ("Bougies", "")
    assert connector.resolve_rayon("Bougies") == ("Divers", None)


def test_rayon_filled_later_in_the_sheet_is_read_after_cache_invalidation(connector, sheet):
    connector.learn_ingredient_rayon("Bougies", "")
    ws = sheet.worksheet("Ingredients_Rayons")
    ws.update_cell(len(ws.rows), 2, "Entretien")  # tri manuel dans le classeur

    connector.invalidate_cache("rayons")

    assert connector.resolve_rayon("Bougies") == ("Entretien", None)


def test_rayons_catalogue_expires_after_the_cache_ttl(connector, sheet, monkeypatch):
    import app.connectors.sheets.meals_connector as module

    assert connector.resolve_rayon("Bougies")[1] is not None
    sheet.worksheet("Ingredients_Rayons").append_row(["Bougies", "Entretien"])  # ajout manuel dans le classeur
    assert connector.resolve_rayon("Bougies")[1] is not None  # encore en cache

    real_time = module.time.time
    monkeypatch.setattr(module.time, "time", lambda: real_time() + connector._cache_ttl_seconds + 1)

    assert connector.resolve_rayon("Bougies") == ("Entretien", None)


def test_get_learned_rayon_reads_the_sheet_and_ignores_unknown_articles(connector):
    connector.learn_ingredient_rayon("Bougies", "")

    assert connector.get_learned_rayon("bougies") == ""
    assert connector.get_learned_rayon("Lait") == "Frais"
    assert connector.get_learned_rayon("Papier cadeau") is None


def test_forget_removes_the_last_matching_row_and_the_article_is_unknown_again(connector, sheet):
    before = _ingredient_rows(sheet)
    connector.learn_ingredient_rayon("Papier cadeau", "Entretien")

    assert connector.forget_ingredient_rayon("papier cadeau") is True

    assert _ingredient_rows(sheet) == before
    assert connector.resolve_rayon("Papier cadeau")[1] is not None
    assert connector.forget_ingredient_rayon("Papier cadeau") is False
