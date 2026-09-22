"""Tests unitaires pour l'adaptateur webhook mobile et l'interopérabilité Android."""
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_api_key(monkeypatch):
    """Par défaut en test, api_key est vide sauf pour les tests spécifiques d'authentification."""
    monkeypatch.setattr(settings, "api_key", "")


def test_interact_accepts_text_alias_instead_of_query():
    """Vérifie que /api/v1/interact accepte un payload avec 'text' au lieu de 'query'."""
    response = client.post(
        "/api/v1/interact",
        json={"text": "Qu'est-ce qu'on mange ce soir ?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "repas" in data["spoken_response"].lower() or "prévu" in data["spoken_response"].lower()


def test_interact_accepts_message_alias():
    """Vérifie que /api/v1/interact accepte un payload avec 'message'."""
    response = client.post(
        "/api/v1/interact",
        json={"message": "Qu'est-ce qu'on mange ce soir ?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


def test_interaction_response_contains_speech_and_text_computed_fields():
    """Vérifie que la réponse JSON contient les alias 'speech' et 'text' pour les moteurs TTS Android."""
    response = client.post(
        "/api/v1/interact",
        json={"query": "bonjour"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "spoken_response" in data
    assert "speech" in data
    assert "text" in data
    assert data["speech"] == data["spoken_response"]
    assert data["text"] == data["spoken_response"]


def test_mobile_endpoint_json_interaction():
    """Vérifie le fonctionnement de l'endpoint dédié /api/v1/mobile/interact en JSON."""
    response = client.post(
        "/api/v1/mobile/interact",
        json={"text": "Qu'est-ce qu'on mange ce soir ?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "speech" in data


def test_mobile_endpoint_plain_text_response_via_accept_header():
    """Vérifie que /api/v1/mobile/interact renvoie du texte brut si Accept: text/plain est spécifié."""
    response = client.post(
        "/api/v1/mobile/interact",
        headers={"Accept": "text/plain"},
        json={"text": "bonjour"},
    )
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "bonjour" in response.text.lower()


def test_mobile_endpoint_get_method_for_simple_shortcuts():
    """Vérifie que /api/v1/mobile/interact supporte GET avec query param pour les raccourcis ultra-légers."""
    response = client.get(
        "/api/v1/mobile/interact",
        params={"text": "bonjour"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


def test_mobile_endpoint_empty_input_graceful_handling():
    """Vérifie qu'un texte vide ne déclenche pas une erreur 422 mais une réponse vocale courtoise."""
    response = client.post(
        "/api/v1/mobile/interact",
        json={"text": ""},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "entendu" in data["spoken_response"].lower() or "compris" in data["spoken_response"].lower()


def test_mobile_endpoint_secured_by_api_key_when_configured(monkeypatch):
    """Vérifie que /api/v1/mobile/interact respecte la sécurité API Key si configurée."""
    monkeypatch.setattr(settings, "api_key", "mobile-secret-key")

    # Sans clé -> 401
    res_unauth = client.post("/api/v1/mobile/interact", json={"text": "bonjour"})
    assert res_unauth.status_code == 401

    # Avec clé -> 200
    res_auth = client.post(
        "/api/v1/mobile/interact",
        headers={"X-API-Key": "mobile-secret-key"},
        json={"text": "bonjour"},
    )
    assert res_auth.status_code == 200
