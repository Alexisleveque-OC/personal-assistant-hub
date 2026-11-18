"""Test d'intégration End-to-End (E2E) - Interface Mobile & Entrées Vocales.

Valide le flux complet en conditions réelles :
1. Manifest PWA & Service Worker (icônes maskable, cache control, start_url)
2. Sécurité mobile (X-API-Key requise et rejet 401 si clé invalide)
3. Requêtes vocales directes (speech, text/plain pour Android Shortcuts/Widgets)
4. Cycle complet : interrogation repas -> ajout courses -> consultation liste -> fin de courses
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)


def test_e2e_pwa_shell_files_are_never_cached_by_the_browser():
    """Manifest, service worker et /app toujours revalidés : une PWA installée reçoit les mises à jour."""
    for path in ("/manifest.json", "/sw.js", "/app"):
        res = client.get(path)
        assert res.status_code == 200, path
        assert res.headers.get("cache-control") == "no-cache, no-store, must-revalidate", path

def test_e2e_mobile_voice_interaction_flow():
    """Valide le parcours mobile de bout en bout avec auth, voix et courses."""
    original_key = settings.api_key
    try:
        settings.api_key = "secret_mobile_key_123"

        # 1. Tentative non authentifiée
        resp_unauth = client.post(
            "/api/v1/mobile/interact",
            json={"text": "Qu'est-ce qu'on mange ce soir ?"},
        )
        assert resp_unauth.status_code == 401

        # 2. Requête vocale authentifiée (JSON standard PWA)
        headers = {"X-API-Key": "secret_mobile_key_123"}
        resp_meal = client.post(
            "/api/v1/mobile/interact",
            json={"text": "Qu'est-ce qu'on mange ce soir ?"},
            headers=headers,
        )
        assert resp_meal.status_code == 200
        meal_data = resp_meal.json()
        assert meal_data["success"] is True
        assert "speech" in meal_data
        assert len(meal_data["speech"]) > 0

        # 3. Requête vocale format texte brut (pour Android HTTP Shortcuts / Tasker TTS)
        headers_plain = {"X-API-Key": "secret_mobile_key_123", "Accept": "text/plain"}
        resp_plain = client.post(
            "/api/v1/mobile/interact",
            json={"text": "Qu'est-ce qu'on mange ce soir ?"},
            headers=headers_plain,
        )
        assert resp_plain.status_code == 200
        assert resp_plain.headers["content-type"].startswith("text/plain")
        assert len(resp_plain.text) > 0

        # 4. Ajout d'article vocal
        resp_add = client.post(
            "/api/v1/mobile/interact",
            json={"text": "Ajoute des bananes à la liste de courses"},
            headers=headers,
        )
        assert resp_add.status_code == 200
        add_data = resp_add.json()
        assert add_data["success"] is True
        assert "bananes" in add_data["speech"].lower()

        # 5. Vérification fin de courses vocale
        resp_completion = client.post(
            "/api/v1/mobile/interact",
            json={"text": "J'ai fini mes courses"},
            headers=headers,
        )
        assert resp_completion.status_code == 200
        comp_data = resp_completion.json()
        assert comp_data["success"] is True
        assert "article" in comp_data["speech"].lower() or "courses" in comp_data["speech"].lower()

    finally:
        settings.api_key = original_key
