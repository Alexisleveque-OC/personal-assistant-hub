"""Tests unitaires et fonctionnels TDD pour la File d'Attente Hors-Ligne & Synchronisation PWA (Étape 4)."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_frontend_offline_outbox_js_exists_and_exports_key_functions():
    """Vérifie que offline_outbox.js est servi et exporte les méthodes essentielles de gestion de la file d'attente."""
    res = client.get("/static/js/offline_outbox.js")
    assert res.status_code == 200, f"Erreur chargement offline_outbox.js: {res.status_code}"
    content = res.text

    # Fonctions d'enfilement (enqueue)
    assert "enqueueTextRequest" in content
    assert "enqueueAudioRequest" in content

    # Fonctions de synchronisation et inspection
    assert "syncOutbox" in content
    assert "getPendingOutboxCount" in content or "getPendingRequests" in content
    assert "initOfflineSync" in content
    assert "updateOutboxIndicator" in content


def test_frontend_index_html_contains_offline_outbox_indicator():
    """Vérifie que index.html contient un témoin visuel dédié pour les requêtes en attente de synchronisation."""
    res = client.get("/app")
    assert res.status_code == 200
    html = res.text

    assert 'id="offline-outbox-indicator"' in html or 'class="offline-outbox-badge"' in html


def test_frontend_chat_view_integrates_offline_outbox_fallback():
    """Vérifie que chat_view.js importe et utilise l'outbox en cas d'échec réseau ou mode hors-ligne."""
    res = client.get("/static/js/views/chat_view.js")
    assert res.status_code == 200
    content = res.text

    assert "offline_outbox.js" in content
    assert "enqueueTextRequest" in content or "enqueueAudioRequest" in content
    assert "hors-ligne" in content.lower() or "enregistré localement" in content.lower() or "hors ligne" in content.lower()


def test_frontend_app_js_initializes_offline_sync():
    """Vérifie que app.js initialise le gestionnaire de synchronisation hors-ligne au chargement."""
    res = client.get("/static/app.js")
    assert res.status_code == 200
    content = res.text

    assert "initOfflineSync" in content or "offline_outbox.js" in content


def test_frontend_offline_outbox_auto_retry_and_sync_triggers():
    """Vérifie la présence d'auto-retry périodique et de multiples déclencheurs (visibility, focus, online)."""
    res = client.get("/static/js/offline_outbox.js")
    assert res.status_code == 200
    content = res.text

    assert "startAutoRetry" in content
    assert "stopAutoRetry" in content
    assert "visibilitychange" in content
    assert "online" in content


def test_service_worker_caches_offline_outbox_and_handles_api_failure():
    """Vérifie que sw.js v20 met en cache offline_outbox.js et ne masque pas les pannes réseau sous un 200."""
    res = client.get("/sw.js")
    assert res.status_code == 200
    content = res.text

    assert "pah-pwa-cache-v24" in content
    assert "/static/js/offline_outbox.js" in content
    assert "status: 503" in content
