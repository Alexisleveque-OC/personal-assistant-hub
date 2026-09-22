"""Configuration globale et fixtures partagées pour Pytest."""
import pytest
from app.config import settings


@pytest.fixture(autouse=True)
def isolate_test_environment(monkeypatch):
    """Isole l'environnement de test pour ne pas dépendre des variables du .env local.
    
    Par défaut, api_key est réinitialisée à vide pour les tests de connecteurs métier,
    les tests spécifiques d'authentification (test_auth.py) la surchargent explicitement.
    """
    monkeypatch.setattr(settings, "api_key", "")
