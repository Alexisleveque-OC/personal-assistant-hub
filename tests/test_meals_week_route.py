"""Refonte UX (Étape 6, retours du 17/11) : GET /api/v1/meals/week?offset=N lit l'onglet annuel par dates.

offset 0 = semaine (samedi → vendredi) contenant aujourd'hui à Paris ; ±N = semaines suivantes / précédentes."""
from datetime import date
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.connectors.sheets.meals_connector import DayMealPlanNotFoundError, PlanningWorksheetNotFoundError
from app.connectors.sheets.models import MealWeekDay
from app.main import app, set_meals_connector
from app.routers import meals as meals_router

client = TestClient(app)


@pytest.fixture
def connector(monkeypatch):
    monkeypatch.setattr(meals_router, "paris_today", lambda: date(2026, 11, 17))
    mock = MagicMock()
    mock.get_meal_week.side_effect = lambda start, today: [
        MealWeekDay(date=start, day_label="sam. x", is_today=start == today)
    ]
    set_meals_connector(mock)  # remis par la fixture autouse en fin de test
    return mock


def test_current_week_starts_on_the_saturday_before_today(connector):
    res = client.get("/api/v1/meals/week")

    assert res.status_code == 200, res.text
    body = res.json()
    connector.get_meal_week.assert_called_once_with(date(2026, 11, 14), today=date(2026, 11, 17))
    assert body["offset"] == 0
    assert (body["start"], body["end"]) == ("2026-11-14", "2026-11-20")
    assert body["week_plan"][0]["date"] == "2026-11-14"


def test_offset_moves_to_the_next_or_previous_weeks(connector):
    assert client.get("/api/v1/meals/week?offset=1").json()["start"] == "2026-11-21"
    assert client.get("/api/v1/meals/week?offset=-2").json()["start"] == "2026-10-31"


def test_offset_is_bounded(connector):
    assert client.get("/api/v1/meals/week?offset=1000").status_code == 422


@pytest.mark.parametrize("error", [
    PlanningWorksheetNotFoundError("L'onglet de planning annuel 'repas 2027' est introuvable"),
    DayMealPlanNotFoundError("La date 19/11/2026 est absente de l'onglet 'repas 2026'"),
])
def test_missing_sheet_or_date_is_a_404_with_the_connector_message(connector, error):
    connector.get_meal_week.side_effect = error

    res = client.get("/api/v1/meals/week?offset=7")

    assert res.status_code == 404
    assert res.json()["detail"] == str(error)
