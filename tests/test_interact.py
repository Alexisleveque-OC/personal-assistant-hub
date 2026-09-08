"""Tests fonctionnels de l'endpoint d'interaction universel."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_interact_meal_plan():
    response = client.post("/api/v1/interact", json={"query": "Qu'est-ce qu'on mange ce soir ?"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "repas" in data["spoken_response"].lower() or "lasagnes" in data["spoken_response"].lower()
    assert data["intent"]["intent"] == "get_meal_plan"


def test_interact_shopping_add():
    response = client.post(
        "/api/v1/interact",
        json={"query": "Ajoute du beurre à la liste de courses"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "beurre" in data["spoken_response"]
    assert data["intent"]["intent"] == "add_shopping_item"


def test_interact_budget_query():
    response = client.post(
        "/api/v1/interact",
        json={"query": "Combien il reste de budget courses ?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "budget courses" in data["spoken_response"]
