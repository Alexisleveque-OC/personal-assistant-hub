"""Tests unitaires pour l'ajout multi-articles et la préservation des cases à cocher dans Liste_Attente."""
from unittest.mock import MagicMock
import pytest

from app.core.intent_parser import IntentParser
from app.core.models import IntentType, InteractionRequest
from app.connectors.sheets.meals_connector import MealsShoppingConnector
from app.main import app, set_meals_connector
from fastapi.testclient import TestClient

client = TestClient(app)
parser = IntentParser()


def test_intent_parser_splits_two_items_with_et():
    """'ajoute du pain et du beurre' doit extraire ['pain', 'beurre']."""
    res = parser.parse("ajoute du pain et du beurre")
    assert res.intent == IntentType.ADD_SHOPPING_ITEM
    assert "items" in res.parameters
    assert res.parameters["items"] == ["pain", "beurre"]
    assert res.parameters["item"] == "pain"  # Rétrocompatibilité


def test_intent_parser_splits_multiple_items_with_commas_and_et():
    """'ajoute des pommes, des poires et du lait' extrait ['pommes', 'poires', 'lait']."""
    res = parser.parse("ajoute des pommes, des poires et du lait")
    assert res.intent == IntentType.ADD_SHOPPING_ITEM
    assert res.parameters["items"] == ["pommes", "poires", "lait"]


def test_intent_parser_splits_with_rajoute_and_partitives():
    """'rajoute du café, du thé ainsi que du chocolat' extrait ['café', 'thé', 'chocolat']."""
    res = parser.parse("rajoute du café, du thé ainsi que du chocolat")
    assert res.intent == IntentType.ADD_SHOPPING_ITEM
    assert res.parameters["items"] == ["café", "thé", "chocolat"]


def test_intent_parser_single_item_backward_compatibility():
    """'ajoute du pain' extrait ['pain'] et conserve item='pain'."""
    res = parser.parse("ajoute du pain")
    assert res.intent == IntentType.ADD_SHOPPING_ITEM
    assert res.parameters["items"] == ["pain"]
    assert res.parameters["item"] == "pain"


def test_connector_add_shopping_items_appends_multiple_rows_with_checkbox():
    """Vérifie que connector.add_shopping_items insère une ligne par article avec case à cocher."""
    connector = MealsShoppingConnector.__new__(MealsShoppingConnector)
    connector._spreadsheet = MagicMock()
    connector._rayons_cache = {"pain": "Boulangerie", "beurre": "Fromage/Beurre/Creme"}
    ws_mock = MagicMock()
    ws_mock.id = 670798145
    connector._spreadsheet.worksheet.return_value = ws_mock

    items, warnings = connector.add_shopping_items(["Pain", "Beurre"])

    assert len(items) == 2
    assert items[0].item == "Pain"
    assert items[1].item == "Beurre"
    # Vérifie que append_row ou append_rows a été appelé avec value_input_option='USER_ENTERED' et booléen False
    assert ws_mock.append_rows.called or ws_mock.append_row.call_count == 2
    if ws_mock.append_rows.called:
        args, kwargs = ws_mock.append_rows.call_args
        assert kwargs.get("value_input_option") == "USER_ENTERED"
        rows = args[0]
        assert rows[0][0] is False or rows[0][0] == False
        assert rows[1][0] is False or rows[1][0] == False


def test_interact_multi_items_spoken_response():
    """Vérifie la formulation vocale lorsqu'on ajoute plusieurs articles."""
    mock_connector = MagicMock()
    from app.connectors.sheets.models import WaitingListItem
    mock_connector.add_shopping_items.return_value = (
        [
            WaitingListItem(item="Pain", is_bought=False, added_at="22/09/2026", rayon="Boulangerie"),
            WaitingListItem(item="Beurre", is_bought=False, added_at="22/09/2026", rayon="Fromage/Beurre/Creme"),
        ],
        [],
    )
    set_meals_connector(mock_connector)

    response = client.post("/api/v1/interact", json={"query": "ajoute du pain et du beurre"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "2 article(s)" in data["spoken_response"] or "2 articles" in data["spoken_response"]
    assert "Pain" in data["spoken_response"]
    assert "Beurre" in data["spoken_response"]
