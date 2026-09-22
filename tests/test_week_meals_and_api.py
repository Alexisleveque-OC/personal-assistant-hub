from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from app.main import app, set_meals_connector
from app.connectors.sheets.meals_connector import MealsShoppingConnector
from app.connectors.sheets.models import DayMealPlan

client = TestClient(app)


def test_interact_concise_spoken_response_for_tomorrow():
    """Vérifie que la réponse vocale pour 'demain soir' est fluide et concise

    sans la formule lourde 'D'après le planning des repas pour...'.
    """
    mock_connector = MagicMock()
    mock_connector.get_meal_plan.return_value = DayMealPlan(
        date_str="23/09/2026",
        day_name="Mercredi",
        dinner="Quiche lorraine + Salade d'endive",
    )
    set_meals_connector(mock_connector)

    res = client.post("/api/v1/interact", json={"query": "Qu'est-ce qu'on mange demain soir ?"})
    assert res.status_code == 200
    spoken = res.json()["spoken_response"]

    # Doit contenir le plat
    assert "Quiche lorraine" in spoken
    # Doit être fluide et concis
    assert "D'après le planning des repas pour" not in spoken
    assert "demain soir" in spoken.lower() or "demain" in spoken.lower()

    set_meals_connector(None)


def test_interact_shopping_list_contains_both_nested_and_top_level_keys():
    """Vérifie que la réponse data contient 'waiting_list' et 'current_week_items'

    directement accessible pour le frontend PWA.
    """
    mock_connector = MagicMock()
    mock_connector.get_shopping_list.return_value = {
        "waiting_list": [],
        "current_week_items": [],
    }
    set_meals_connector(mock_connector)

    res = client.post("/api/v1/interact", json={"query": "Donne-moi la liste de courses"})
    assert res.status_code == 200
    data = res.json()["data"]
    assert "waiting_list" in data
    assert "current_week_items" in data

    set_meals_connector(None)


def test_get_week_meals_endpoint():
    """Vérifie l'endpoint /api/v1/meals/week qui fournit le planning de la semaine."""
    mock_connector = MagicMock()
    mock_connector.get_week_meal_plans.return_value = [
        {
            "day_label": "mar. 22",
            "day_name": "Mardi",
            "date_str": "22/09/2026",
            "lunch": None,
            "lunch_ingredients": [],
            "dinner": "Riz cantonnais",
            "dinner_ingredients": ["Riz", "Oeufs", "Jambon", "Petit pois"],
            "is_today": True,
        }
    ]
    set_meals_connector(mock_connector)

    res = client.get("/api/v1/meals/week")
    assert res.status_code == 200
    data = res.json()
    assert "week_plan" in data
    assert len(data["week_plan"]) >= 1
    assert data["week_plan"][0]["dinner"] == "Riz cantonnais"

    set_meals_connector(None)
