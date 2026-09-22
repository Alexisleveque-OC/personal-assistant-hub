"""Tests unitaires pour l'authentification et la sécurisation par clé API (X-API-Key)."""
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


def test_public_endpoints_accessible_without_api_key(monkeypatch):
    """Vérifie que les endpoints système et documentation restent accessibles publiquement."""
    monkeypatch.setattr(settings, "api_key", "super-secret-key-123")

    # Racine et health check
    res_root = client.get("/")
    assert res_root.status_code == 200

    res_health = client.get("/health")
    assert res_health.status_code == 200

    # OpenAPI schema
    res_openapi = client.get("/openapi.json")
    assert res_openapi.status_code == 200


def test_api_v1_rejected_when_api_key_configured_and_missing(monkeypatch):
    """Vérifie qu'une requête sans header X-API-Key est rejetée (401) si une clé est configurée."""
    monkeypatch.setattr(settings, "api_key", "super-secret-key-123")

    response = client.post(
        "/api/v1/interact",
        json={"query": "Qu'est-ce qu'on mange ce soir ?"},
    )
    assert response.status_code == 401
    assert "api key" in response.json().get("detail", "").lower()


def test_api_v1_rejected_when_api_key_invalid(monkeypatch):
    """Vérifie qu'une requête avec une mauvaise clé X-API-Key est rejetée (401)."""
    monkeypatch.setattr(settings, "api_key", "super-secret-key-123")

    response = client.post(
        "/api/v1/interact",
        headers={"X-API-Key": "mauvaise-cle"},
        json={"query": "Qu'est-ce qu'on mange ce soir ?"},
    )
    assert response.status_code == 401
    assert "api key" in response.json().get("detail", "").lower()


def test_api_v1_accepted_when_api_key_valid(monkeypatch):
    """Vérifie qu'une requête avec la bonne clé X-API-Key est acceptée (200)."""
    monkeypatch.setattr(settings, "api_key", "super-secret-key-123")

    response = client.post(
        "/api/v1/interact",
        headers={"X-API-Key": "super-secret-key-123"},
        json={"query": "Qu'est-ce qu'on mange ce soir ?"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_api_v1_permissive_when_api_key_not_configured(monkeypatch):
    """Vérifie qu'en mode local permissif (api_key vide), les requêtes passent sans header."""
    monkeypatch.setattr(settings, "api_key", "")

    response = client.post(
        "/api/v1/interact",
        json={"query": "Qu'est-ce qu'on mange ce soir ?"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
