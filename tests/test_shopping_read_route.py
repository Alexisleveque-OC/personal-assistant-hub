"""Refonte UX (ROADMAP Étape 1) : l'accueil lit la liste de courses sans passer par Otis.

Avant, la PWA demandait « Donne-moi la liste de courses » à /interact : chaque ouverture écrivait dans le journal
des conversations et dans l'historique de la session."""
from fastapi.testclient import TestClient

from app.connectors.sheets.models import ShoppingItem, WaitingListItem
from app.main import app, set_meals_connector

client = TestClient(app)


def test_shopping_list_is_read_directly_from_the_connector(isolate_test_environment):
    connector = isolate_test_environment
    connector.get_shopping_list.return_value = {
        "waiting_list": [WaitingListItem(item="Lessive", is_bought=False, rayon="Entretien")],
        "current_week_items": [ShoppingItem(name="Banane", checked=False), ShoppingItem(name="Pomme", checked=True)],
        "rayons_order": ["Fruits"],
    }

    res = client.get("/api/v1/meals/shopping")

    assert res.status_code == 200, res.text
    body = res.json()
    assert [i["name"] for i in body["current_week_items"]] == ["Banane", "Pomme"]
    assert body["current_week_items"][1]["checked"] is True
    assert body["waiting_list"][0]["item"] == "Lessive"


def test_shopping_list_without_connector_fails_with_an_explicit_message():
    set_meals_connector(None)  # remis par la fixture autouse en fin de test

    res = client.get("/api/v1/meals/shopping")

    assert res.status_code == 503
    assert "courses" in res.json()["detail"].lower()
