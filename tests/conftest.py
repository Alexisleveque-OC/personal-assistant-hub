"""Configuration globale et fixtures partagées pour Pytest."""
import pytest
from unittest.mock import MagicMock
from app.config import settings
from app.main import set_meals_connector
from app.connectors.sheets.models import DayMealPlan, ShoppingItem, WaitingListItem


@pytest.fixture(autouse=True)
def isolate_test_environment(request, monkeypatch):
    """Isole l'environnement de test pour garantir ZÉRO effet de bord sur le Google Sheet réel.
    
    1. Réinitialise api_key à vide par défaut (surchargée explicitement par les tests d'auth).
    2. Pour tous les tests ordinaires (sauf ceux marqués avec @pytest.mark.live_sheets) :
       - Injecte automatiquement un mock in-memory complet via set_meals_connector().
       - Isole l'ID du tableur.
    """
    monkeypatch.setattr(settings, "api_key", "")

    # Si le test est explicitement marqué live_sheets, on le laisse accéder à son environnement configuré
    if "live_sheets" in request.keywords:
        yield
        return

    # Mock in-memory réaliste par défaut
    mock_connector = MagicMock()
    mock_connector.is_mock = True

    # Comportements par défaut cohérents
    mock_connector.get_meal_plan.return_value = DayMealPlan(
        date_str="25/09/2026",
        day_name="Vendredi",
        lunch="Salade composée",
        dinner="Pizza maison",
    )
    mock_connector.get_shopping_list.return_value = {
        "waiting_list": [],
        "current_week_items": [],
    }

    def _mock_add_shopping_item(item, rayon="Divers"):
        return WaitingListItem(item=item, is_bought=False, rayon=rayon), None

    def _mock_add_shopping_items(items):
        added = [WaitingListItem(item=it, is_bought=False, rayon="Divers") for it in items]
        return added, []

    mock_connector.add_shopping_item.side_effect = _mock_add_shopping_item
    mock_connector.add_shopping_items.side_effect = _mock_add_shopping_items
    mock_connector.mark_shopping_items_bought.side_effect = lambda items: list(items)
    mock_connector.clear_shopping_list.return_value = 1
    mock_connector.get_recipe_ingredients.return_value = None

    set_meals_connector(mock_connector)

    try:
        yield mock_connector
    finally:
        set_meals_connector(None)
