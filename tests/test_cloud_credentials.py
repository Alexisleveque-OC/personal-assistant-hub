"""Tests unitaires pour l'authentification Google Cloud sans fichier physique."""

import base64
import json
from unittest.mock import patch, MagicMock
import pytest
from app.config import Settings
from app.connectors.sheets.meals_connector import MealsShoppingConnector


SAMPLE_SA_DICT = {
    "type": "service_account",
    "project_id": "test-project-123",
    "private_key_id": "key123",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC3\n-----END PRIVATE KEY-----\n",
    "client_email": "test-sa@test-project-123.iam.gserviceaccount.com",
    "client_id": "123456789",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
}


def test_settings_has_google_service_account_info_field():
    """Vérifie que le modèle Settings supporte la variable d'environnement Cloud."""
    s = Settings(google_service_account_info='{"type": "service_account"}')
    assert s.google_service_account_info == '{"type": "service_account"}'


@patch("app.connectors.sheets.meals_connector.gspread")
def test_meals_connector_uses_service_account_info_json(mock_gspread):
    """Vérifie que MealsShoppingConnector s'authentifie via JSON brut en variable d'environnement."""
    mock_client = MagicMock()
    mock_gspread.service_account_from_dict.return_value = mock_client
    mock_client.open_by_key.return_value = MagicMock()

    json_str = json.dumps(SAMPLE_SA_DICT)

    with patch("app.connectors.sheets.meals_connector.settings") as mock_settings:
        mock_settings.google_service_account_info = json_str
        mock_settings.spreadsheet_meals_shopping_id = "test_sheet_id"

        connector = MealsShoppingConnector()

        mock_gspread.service_account_from_dict.assert_called_once_with(SAMPLE_SA_DICT)
        mock_client.open_by_key.assert_called_once_with("test_sheet_id")


@patch("app.connectors.sheets.meals_connector.gspread")
def test_meals_connector_uses_service_account_info_base64(mock_gspread):
    """Vérifie que MealsShoppingConnector supporte aussi le format base64."""
    mock_client = MagicMock()
    mock_gspread.service_account_from_dict.return_value = mock_client
    mock_client.open_by_key.return_value = MagicMock()

    json_str = json.dumps(SAMPLE_SA_DICT)
    b64_str = base64.b64encode(json_str.encode("utf-8")).decode("ascii")

    with patch("app.connectors.sheets.meals_connector.settings") as mock_settings:
        mock_settings.google_service_account_info = b64_str
        mock_settings.spreadsheet_meals_shopping_id = "test_sheet_id"

        connector = MealsShoppingConnector()

        mock_gspread.service_account_from_dict.assert_called_once_with(SAMPLE_SA_DICT)
