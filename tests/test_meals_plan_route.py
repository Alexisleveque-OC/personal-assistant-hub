"""Feuille Repas (retours du 17/11) : « Supprimer » efface le plat tout de suite (sans Otis) ; « Annuler » le remet.

DELETE /api/v1/meals/plan/{date}/{moment} renvoie le plat retiré ; PUT … {plat} le réécrit tel quel."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.connectors.sheets.meals_connector import MealsShoppingConnector
from app.main import app, set_meals_connector
from tests.meals_fakes import MealsSheetState, build_meals_spreadsheet, planned_meals

client = TestClient(app)
DAY = date(2026, 11, 17)


@pytest.fixture
def sheet():
    spreadsheet = build_meals_spreadsheet(MealsSheetState(
        today=DAY, meals={DAY: ("Quiche lorraine + Coleslaw", "Carotte Bolognaise")},
    ))
    set_meals_connector(MealsShoppingConnector(spreadsheet=spreadsheet))  # remis par la fixture autouse
    return spreadsheet


def test_delete_empties_the_slot_and_returns_the_removed_dish(sheet):
    res = client.delete("/api/v1/meals/plan/2026-11-17/midi")

    assert res.status_code == 200, res.text
    assert res.json() == {"date": "2026-11-17", "moment": "midi", "precedent": "Quiche lorraine + Coleslaw"}
    assert planned_meals(sheet)["17/11/2026"] == ("", "Carotte Bolognaise")


def test_put_restores_the_dish_exactly(sheet):
    client.delete("/api/v1/meals/plan/2026-11-17/soir")

    res = client.put("/api/v1/meals/plan/2026-11-17/soir", json={"plat": "Carotte Bolognaise"})

    assert res.status_code == 200, res.text
    assert planned_meals(sheet)["17/11/2026"] == ("Quiche lorraine + Coleslaw", "Carotte Bolognaise")


def test_delete_an_empty_slot_is_a_404(sheet):
    client.delete("/api/v1/meals/plan/2026-11-17/midi")

    res = client.delete("/api/v1/meals/plan/2026-11-17/midi")

    assert res.status_code == 404
    assert "Rien de prévu" in res.json()["detail"]


def test_a_date_missing_from_the_sheet_is_a_404(sheet):
    res = client.delete("/api/v1/meals/plan/2026-03-01/midi")

    assert res.status_code == 404
    assert "01/03/2026" in res.json()["detail"]


@pytest.mark.parametrize("call", [
    lambda: client.delete("/api/v1/meals/plan/2026-11-17/gouter"),
    lambda: client.put("/api/v1/meals/plan/2026-11-17/midi", json={"plat": "  "}),
])
def test_invalid_moment_or_blank_dish_is_rejected(sheet, call):
    assert call().status_code == 422
