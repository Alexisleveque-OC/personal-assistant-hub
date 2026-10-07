"""Tests unitaires pour la réinitialisation de la liste de courses et le cycle hebdomadaire."""
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.dependencies import set_meals_connector
from app.connectors.sheets.meals_connector import MealsShoppingConnector
from app.config import settings

client = TestClient(app)


def test_uncheck_current_week_items_in_connector():
    """Vérifie que connector.uncheck_current_week_items passe les cases TRUE à FALSE dans 'Cette semaine'."""
    connector = MealsShoppingConnector.__new__(MealsShoppingConnector)
    connector._spreadsheet = MagicMock()
    connector._shopping_cache = {"some": "data"}
    connector._shopping_cache_time = 12345.0
    connector._cache_ttl_seconds = 180

    ws_mock = MagicMock()
    # Simuler 12 lignes : 1-8 pour le planning, 9+ pour les courses
    # Col 0: TRUE, Col 1: Pommes, Col 2: FALSE, Col 3: Poires, Col 4: TRUE, Col 5: Poulet
    rows = [
        ["Planning"] * 8,
        ["sam. 19", "", "Repas 1", "", "Repas 2", ""],
        ["dim. 20", "", "", "", "", ""],
        ["lun. 21", "", "", "", "", ""],
        ["mar. 22", "", "", "", "", ""],
        ["mer. 23", "", "", "", "", ""],
        ["jeu. 24", "", "", "", "", ""],
        ["ven. 25", "", "", "", "", ""],
        ["Rayon Fruits", "", "Rayon Boucherie", "", "", ""],  # Ligne 9 (index 8)
        ["TRUE", "Pommes", "FALSE", "Poires", "TRUE", "Poulet"],  # Ligne 10 (index 9)
        ["FALSE", "Bananes", "", "", "", ""],  # Ligne 11 (index 10)
    ]
    ws_mock.get_all_values.return_value = rows
    connector._spreadsheet.worksheet.return_value = ws_mock

    # Appel de la méthode
    count = connector.uncheck_current_week_items()

    assert count == 2  # Pommes (TRUE) et Poulet (TRUE)
    assert ws_mock.update_cell.call_count == 2
    # Ligne 10: Pommes en col A (1) -> update_cell(10, 1, False)
    # Ligne 10: Poulet en col E (5) -> update_cell(10, 5, False)
    ws_mock.update_cell.assert_any_call(10, 1, False)
    ws_mock.update_cell.assert_any_call(10, 5, False)
    # Vérifie que le cache a été invalidé
    assert getattr(connector, "_shopping_cache", None) is None


def test_reset_shopping_endpoint():
    """Vérifie que l'endpoint POST /api/v1/meals/shopping/reset appelle le connecteur et retourne 200."""
    mock_connector = MagicMock()
    mock_connector.uncheck_current_week_items.return_value = 3
    set_meals_connector(mock_connector)

    headers = {"X-API-Key": settings.api_key} if settings.api_key else {}
    response = client.post("/api/v1/meals/shopping/reset", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["uncheck_count"] == 3
    assert "réinitialisée" in data["message"].lower()
    mock_connector.uncheck_current_week_items.assert_called_once()
    mock_connector.invalidate_cache.assert_called()


def test_mark_current_week_items_bought_in_connector():
    """Vérifie que connector.mark_current_week_items_bought passe les cases FALSE à TRUE dans 'Cette semaine'."""
    connector = MealsShoppingConnector.__new__(MealsShoppingConnector)
    connector._spreadsheet = MagicMock()
    connector._shopping_cache = {"some": "data"}
    connector._shopping_cache_time = 12345.0
    connector._cache_ttl_seconds = 180

    ws_mock = MagicMock()
    # Simuler 12 lignes : 1-8 pour le planning, 9+ pour les courses
    rows = [
        ["Planning"] * 8,
        ["sam. 19", "", "Repas 1", "", "Repas 2", ""],
        ["dim. 20", "", "", "", "", ""],
        ["lun. 21", "", "", "", "", ""],
        ["mar. 22", "", "", "", "", ""],
        ["mer. 23", "", "", "", "", ""],
        ["jeu. 24", "", "", "", "", ""],
        ["ven. 25", "", "", "", "", ""],
        ["Rayon Fruits", "", "Rayon Boucherie", "", "", ""],  # Ligne 9 (index 8)
        ["FALSE", "Pommes", "FALSE", "Poires", "FALSE", "Poulet"],  # Ligne 10 (index 9)
        ["FALSE", "Bananes", "", "", "", ""],  # Ligne 11 (index 10)
    ]
    ws_mock.get_all_values.return_value = rows
    connector._spreadsheet.worksheet.return_value = ws_mock

    # Appel de la méthode pour marquer Pommes et Poulet
    marked = connector.mark_current_week_items_bought(["Pommes", "Poulet"])

    assert len(marked) == 2
    assert "Pommes" in marked
    assert "Poulet" in marked
    # Vérifie que le cache a été invalidé
    assert getattr(connector, "_shopping_cache", None) is None


def test_complete_shopping_endpoint():
    """Vérifie que l'endpoint POST /api/v1/meals/shopping/complete synchronise Cette semaine et Liste_Attente."""
    mock_connector = MagicMock()
    mock_connector.mark_current_week_items_bought.return_value = ["Pommes", "Poulet"]
    mock_connector.mark_shopping_items_bought.return_value = ["Café bio"]
    set_meals_connector(mock_connector)

    headers = {"X-API-Key": settings.api_key} if settings.api_key else {}
    payload = {
        "current_week_items": ["Pommes", "Poulet"],
        "waiting_items": ["Café bio"],
    }
    response = client.post("/api/v1/meals/shopping/complete", json=payload, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["marked_current_week"] == ["Pommes", "Poulet"]
    assert data["marked_waiting"] == ["Café bio"]
    mock_connector.mark_current_week_items_bought.assert_called_once_with(["Pommes", "Poulet"])
    mock_connector.mark_shopping_items_bought.assert_called_once_with(["Café bio"])

