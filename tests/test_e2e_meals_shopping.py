"""Test d'intégration End-to-End (E2E) pour le connecteur repas, recettes et courses."""
from datetime import datetime
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app, set_meals_connector
from app.connectors.sheets.meals_connector import MealsShoppingConnector

client = TestClient(app)

requires_live_sheets = pytest.mark.skipif(
    not Path(settings.google_service_account_file).exists()
    or not settings.spreadsheet_meals_shopping_id,
    reason="Identifiants Google Sheets réels non configurés.",
)


@pytest.fixture(scope="module")
def live_connector():
    """Initialise une unique connexion réelle partagée pour l'ensemble des tests E2E."""
    if not Path(settings.google_service_account_file).exists() or not settings.spreadsheet_meals_shopping_id:
        pytest.skip("Identifiants Google Sheets non disponibles")
    connector = MealsShoppingConnector()
    set_meals_connector(connector)
    yield connector
    set_meals_connector(None)


@requires_live_sheets
def test_e2e_get_recipe_ingredients_live(live_connector):
    """Valide la chaîne complète NLU -> Recherche Recette -> Réponse vocale sur le Sheet réel."""
    response = client.post(
        "/api/v1/interact",
        json={"query": "Quels sont les ingrédients pour le risotto de quinoa ?"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["intent"]["intent"] == "get_recipe_ingredients"
    assert "risotto de quinoa" in data["spoken_response"].lower()
    assert "quinoa" in data["spoken_response"].lower()
    assert "courgette" in data["spoken_response"].lower()
    assert "recipe" in data["data"]
    assert "Quinoa" in data["data"]["recipe"]["ingredients"]


@requires_live_sheets
def test_e2e_get_festive_recipe_ingredients_live(live_connector):
    """Valide la recherche dans l'onglet Recette festive en direct."""
    response = client.post(
        "/api/v1/interact",
        json={"query": "Qu'est-ce qu'il faut pour faire du guacamole ?"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["intent"]["intent"] == "get_recipe_ingredients"
    assert "guacamole" in data["spoken_response"].lower()
    assert "avocat" in data["spoken_response"].lower()


@requires_live_sheets
def test_e2e_get_shopping_list_live(live_connector):
    """Valide la consultation de la liste de courses en direct (Cette semaine + Liste_Attente)."""
    response = client.post(
        "/api/v1/interact",
        json={"query": "Donne-moi la liste de courses"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["intent"]["intent"] == "get_shopping_list"
    assert "shopping_list" in data["data"]
    assert "waiting_list" in data["data"]["shopping_list"]
    assert "current_week_items" in data["data"]["shopping_list"]


@requires_live_sheets
def test_e2e_shopping_item_lifecycle_live(live_connector):
    """Valide le cycle de vie complet d'un article sur le Google Sheet réel :
    
    1. Ajout dans Liste_Attente
    2. Marquage comme acheté
    3. Nettoyage de la liste (suppression propre)
    """
    timestamp = int(datetime.now().timestamp())
    test_item = f"Café test E2E {timestamp}"

    # 1. Ajout
    r1 = client.post(
        "/api/v1/interact",
        json={"query": f"Ajoute {test_item} à la liste de courses"},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["success"] is True
    assert test_item.lower() in d1["spoken_response"].lower()

    # Vérification que la ligne est présente dans Liste_Attente
    ws = live_connector.spreadsheet.worksheet("Liste_Attente")
    records = ws.get_all_values()
    added_row = next((row for row in records if len(row) > 1 and row[1].strip().lower() == test_item.lower()), None)
    assert added_row is not None
    assert added_row[0].upper() == "FALSE"

    # 2. Marquage acheté
    r2 = client.post(
        "/api/v1/interact",
        json={"query": f"J'ai acheté {test_item}"},
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["success"] is True

    # Vérification que la case est devenue TRUE
    records_after_buy = ws.get_all_values()
    bought_row = next((row for row in records_after_buy if len(row) > 1 and row[1].strip().lower() == test_item.lower()), None)
    assert bought_row is not None
    assert bought_row[0].upper() == "TRUE"

    # 3. Nettoyage
    r3 = client.post(
        "/api/v1/interact",
        json={"query": "Vide la liste de courses"},
    )
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["success"] is True

    # Vérification que l'article temporaire a bien été supprimé
    records_after_clear = ws.get_all_values()
    cleaned_row = next((row for row in records_after_clear if len(row) > 1 and row[1].strip().lower() == test_item.lower()), None)
    assert cleaned_row is None
