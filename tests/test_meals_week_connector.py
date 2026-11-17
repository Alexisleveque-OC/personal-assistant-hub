"""Refonte UX (Étape 6, retours du 17/11) : la feuille Repas lit l'onglet annuel « repas AAAA » par dates.

Avant, elle lisait l'onglet « Cette semaine » (valeurs fixes) : un plat écrit par Otis dans « repas 2026 »
n'apparaissait pas. La lecture par dates permet aussi de naviguer de semaine en semaine (samedi → vendredi)."""
from datetime import date
from unittest.mock import MagicMock

import pytest

from app.connectors.sheets.meals_connector import (
    DayMealPlanNotFoundError,
    MealsShoppingConnector,
    PlanningWorksheetNotFoundError,
    meal_week_start,
)

HEADER = ["Date", "Jour", "Midi", "Soir", "Notes / Magasin"]


def _ws(title, rows):
    ws = MagicMock()
    ws.title = title
    ws.get_all_values.return_value = rows
    return ws


def _connector(sheets):
    recettes = _ws("Recettes", [
        ["Plat", "Catégorie", "Catégorie 2", "Complet", "Ingrédient", "", ""],
        ["Carotte Bolognaise", "Plat", "", "TRUE", "Carottes", "Tomates", "Oignon"],
        ["Salade", "Entrée", "", "FALSE", "Feta", "Concombre", ""],
    ])
    festive = _ws("Recette festive", [["Plat", "Catégorie", "Catégorie 2", "Complet", "Ingrédient"]])
    ws_map = {ws.title: ws for ws in [recettes, festive, *sheets]}
    sh = MagicMock()
    sh.worksheets.return_value = list(ws_map.values())
    sh.worksheet.side_effect = lambda name: ws_map[name]
    return MealsShoppingConnector(spreadsheet=sh)


def _rows(year, start_day, month, n, extra=None):
    rows = [HEADER]
    for i in range(n):
        d = date(year, month, start_day + i)
        rows.append([d.strftime("%d/%m/%Y"), "", *(extra or {}).get(d, ("", "")), ""])
    return rows


def test_week_starts_on_saturday_and_moves_by_whole_weeks():
    assert meal_week_start(date(2026, 11, 17)) == date(2026, 11, 14)  # mardi → samedi précédent
    assert meal_week_start(date(2026, 11, 14)) == date(2026, 11, 14)  # samedi
    assert meal_week_start(date(2026, 11, 20)) == date(2026, 11, 14)  # vendredi
    assert meal_week_start(date(2026, 11, 17), offset=1) == date(2026, 11, 21)
    assert meal_week_start(date(2026, 11, 17), offset=-2) == date(2026, 10, 31)


def test_week_is_read_from_the_annual_sheet_with_labels_ingredients_and_today():
    extra = {date(2026, 11, 17): ("Salade", "Carotte Bolognaise"), date(2026, 11, 18): ("", "Inconnu + Salade")}
    connector = _connector([_ws("repas 2026", _rows(2026, 14, 11, 7, extra))])

    week = connector.get_meal_week(date(2026, 11, 14), today=date(2026, 11, 17))

    assert [d.day_label for d in week] == ["sam. 14", "dim. 15", "lun. 16", "mar. 17", "mer. 18", "jeu. 19", "ven. 20"]
    assert [d.is_today for d in week] == [False, False, False, True, False, False, False]
    tuesday = week[3]
    assert tuesday.date == date(2026, 11, 17)
    assert (tuesday.lunch, tuesday.dinner) == ("Salade", "Carotte Bolognaise")
    assert tuesday.lunch_ingredients == ["Feta", "Concombre"]
    assert tuesday.dinner_ingredients == ["Carottes", "Tomates", "Oignon"]
    assert week[4].dinner_ingredients == ["Feta", "Concombre"]  # plat composé : ingrédients des parties connues
    assert week[0].lunch is None and week[0].lunch_ingredients == []


def test_a_written_meal_shows_up_on_the_next_read():
    rows = _rows(2026, 14, 11, 7)
    sheet = _ws("repas 2026", rows)
    connector = _connector([sheet])
    connector.get_meal_week(date(2026, 11, 14), today=date(2026, 11, 17))

    connector.set_meal_plan(meal="Salade", target_date=date(2026, 11, 17), meal_type="midi")
    rows[4][2] = "Salade"  # ce que contient désormais le classeur

    week = connector.get_meal_week(date(2026, 11, 14), today=date(2026, 11, 17))
    assert week[3].lunch == "Salade"


def test_a_week_across_new_year_reads_both_annual_sheets():
    connector = _connector([
        _ws("repas 2026", [HEADER] + [[f"{d:02d}/12/2026", "", "", "Soupe", ""] for d in range(26, 32)]),
        _ws("repas 2027", [HEADER, ["01/01/2027", "", "Galette", "", ""]]),
    ])

    week = connector.get_meal_week(date(2026, 12, 26), today=date(2026, 12, 28))

    assert [d.day_label for d in week][-2:] == ["jeu. 31", "ven. 1"]
    assert week[-1].lunch == "Galette"


def test_a_missing_annual_sheet_is_reported_explicitly():
    connector = _connector([_ws("repas 2026", [HEADER])])

    with pytest.raises(PlanningWorksheetNotFoundError, match="repas 2027"):
        connector.get_meal_week(date(2027, 1, 2), today=date(2026, 11, 17))


def test_a_missing_date_row_is_reported_explicitly():
    connector = _connector([_ws("repas 2026", _rows(2026, 14, 11, 5))])

    with pytest.raises(DayMealPlanNotFoundError, match="19/11/2026"):
        connector.get_meal_week(date(2026, 11, 14), today=date(2026, 11, 17))
