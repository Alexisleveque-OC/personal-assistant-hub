from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from app.main import app, set_meals_connector
from app.core.models import IntentType
from app.connectors.sheets.models import ShoppingItem, WaitingListItem
from app.core.intent_parser import IntentParser

client = TestClient(app)
parser = IntentParser()


def test_intent_parser_check_shopping_completion():
    """Vérifie la reconnaissance de l'intention de vérification de fin de courses."""
    queries = [
        "est-ce que j'ai bien tout ?",
        "j'ai fini mes courses",
        "j'ai terminé mes courses",
        "ai-je oublié quelque chose ?",
        "est-ce que j'ai tout ?",
        "ai-je tout pris ?",
    ]
    for q in queries:
        parsed = parser.parse(q)
        assert parsed.intent == IntentType.CHECK_SHOPPING_COMPLETION, f"Échec pour la requête '{q}': obtenu {parsed.intent}"


def test_interact_check_shopping_completion_with_remaining():
    """Vérifie le retour vocal lorsqu'il reste des articles non cochés."""
    mock_connector = MagicMock()
    mock_connector.get_shopping_list.return_value = {
        "waiting_list": [WaitingListItem(item="Beurre", is_bought=False)],
        "current_week_items": [
            ShoppingItem(name="Bananes", checked=True),
            ShoppingItem(name="Avocat", checked=False),
        ],
    }
    set_meals_connector(mock_connector)

    res = client.post("/api/v1/interact", json={"query": "est-ce que j'ai bien tout ?"})
    assert res.status_code == 200
    data = res.json()
    assert data["data"]["completed"] is False
    assert len(data["data"]["remaining_items"]) == 2
    assert "Beurre" in data["data"]["remaining_items"]
    assert "Avocat" in data["data"]["remaining_items"]
    assert "reste encore 2 article" in data["spoken_response"]

    set_meals_connector(None)


def test_interact_check_shopping_completion_all_done():
    """Vérifie le retour vocal enthousiaste quand tous les articles sont cochés."""
    mock_connector = MagicMock()
    mock_connector.get_shopping_list.return_value = {
        "waiting_list": [WaitingListItem(item="Beurre", is_bought=True)],
        "current_week_items": [
            ShoppingItem(name="Bananes", checked=True),
            ShoppingItem(name="Avocat", checked=True),
        ],
    }
    set_meals_connector(mock_connector)

    res = client.post("/api/v1/interact", json={"query": "j'ai fini mes courses"})
    assert res.status_code == 200
    data = res.json()
    assert data["data"]["completed"] is True
    assert len(data["data"]["remaining_items"]) == 0
    assert "tout pris" in data["spoken_response"].lower()

    set_meals_connector(None)


def test_meals_connector_caching_and_invalidation():
    """Vérifie que get_shopping_list met en cache et que add_shopping_items invalide le cache."""
    from app.connectors.sheets.meals_connector import MealsShoppingConnector
    connector = MealsShoppingConnector.__new__(MealsShoppingConnector)
    connector._shopping_cache = None
    connector._shopping_cache_time = 0
    connector._rayons_order = None
    connector._recipes_cache = None

    mock_sheet = MagicMock()
    mock_ws = MagicMock()
    mock_ws.get_all_values.return_value = [["TRUE", "Banane"]]
    mock_sheet.worksheet.return_value = mock_ws
    connector._spreadsheet = mock_sheet

    # 1er appel : appelle worksheet
    res1 = connector.get_shopping_list()
    assert mock_sheet.worksheet.called
    call_count = mock_sheet.worksheet.call_count

    # 2eme appel : doit utiliser le cache
    res2 = connector.get_shopping_list()
    assert mock_sheet.worksheet.call_count == call_count  # Aucun nouvel appel gspread

    # Invalidation manuelle / mutation
    connector.invalidate_cache("shopping")
    assert connector._shopping_cache is None
