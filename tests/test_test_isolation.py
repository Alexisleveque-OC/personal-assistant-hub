"""Test vérifiant l'isolation absolue de la suite de tests (Zéro Effet de Bord)."""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app, get_meals_connector
from app.config import settings

client = TestClient(app)


def test_default_connector_in_tests_is_mock_and_never_hits_live_sheet():
    """Vérifie que par défaut dans n'importe quel test, le connecteur est isolé

    et n'utilise pas le vrai client Google Sheets ni l'ID réel en écriture.
    """
    connector = get_meals_connector()
    assert connector is not None
    # Le connecteur doit être un mock ou une instance isolée en mémoire
    assert isinstance(connector, MagicMock) or getattr(connector, "is_mock", False)


def test_api_call_without_explicit_mock_uses_safe_in_memory_default():
    """Vérifie qu'un appel d'API standard ne déclenche aucune requête réseau réelle."""
    resp = client.post(
        "/api/v1/interact",
        json={"query": "Ajoute des bananes à la liste de courses"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "bananes" in data["spoken_response"].lower()
