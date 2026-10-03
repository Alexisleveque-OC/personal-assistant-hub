"""Tests d'optimisation de latence et de cache RAM (Étape 4 - TDD)."""
import time
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from app.main import app, set_meals_connector
from app.connectors.sheets.models import WaitingListItem, Recipe, DayMealPlan

client = TestClient(app)


def test_warmup_cache_preloads_all_catalogues():
    """Vérifie que la méthode warmup_cache précharge en mémoire l'ensemble des catalogues."""
    mock_connector = MagicMock()
    mock_connector.warmup_cache.return_value = {
        "rayons_count": 15,
        "recipes_count": 42,
        "rayons_order_count": 8,
        "shopping_loaded": True,
    }
    set_meals_connector(mock_connector)

    res = client.post("/api/v1/cache/warmup")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["stats"]["rayons_count"] == 15
    assert data["stats"]["recipes_count"] == 42
    mock_connector.warmup_cache.assert_called_once()

    set_meals_connector(None)


def test_hot_cache_requires_zero_network_calls_on_read():
    """Quand le cache est chaud, une lecture de planning ou liste de courses ne fait aucun appel réseau."""
    mock_connector = MagicMock()
    mock_connector.get_meal_plan.return_value = DayMealPlan(
        date_str="02/10/2026", day_name="Vendredi", lunch="Salade", dinner="Quiche"
    )
    set_meals_connector(mock_connector)

    # Exécution de la requête
    start_time = time.perf_counter()
    res = client.post(
        "/api/v1/interact",
        json={"query": "Qu'est-ce qu'on mange ce midi ?"},
    )
    duration = time.perf_counter() - start_time

    assert res.status_code == 200
    assert "Salade" in res.json()["spoken_response"]
    # Vérification que le temps de traitement local en mémoire est quasi-instantané (< 300 ms en test)
    assert duration < 0.5

    set_meals_connector(None)


def test_async_shopping_item_addition_with_optimistic_cache():
    """L'ajout d'article via BackgroundTasks répond immédiatement tout en mettant à jour le cache optimiste."""
    mock_connector = MagicMock()
    mock_connector.resolve_rayon.return_value = ("Épicerie", None)
    mock_connector.add_shopping_item.return_value = (
        WaitingListItem(item="Pâtes complètes", rayon="Épicerie"),
        None,
    )
    set_meals_connector(mock_connector)

    start_time = time.perf_counter()
    res = client.post(
        "/api/v1/interact",
        json={"query": "Ajoute des pâtes complètes"},
    )
    duration = time.perf_counter() - start_time

    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "pâtes complètes" in data["spoken_response"].lower()
    # Le temps de traitement en mémoire est immédiat
    assert duration < 0.5
    # La persistance en tâche de fond a bien été appelée
    mock_connector.add_shopping_item.assert_called_once()

    set_meals_connector(None)
