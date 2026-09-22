from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)


def test_get_app_returns_200_html():
    """Vérifie que la route /app retourne l'interface HTML PWA."""
    response = client.get("/app")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    html = response.text
    assert "<!DOCTYPE html>" in html or "<html" in html
    assert "manifest.json" in html
    assert 'id="mic-btn"' in html
    assert 'id="query-form"' in html
    assert 'id="query-input"' in html
    assert 'id="chat-stream"' in html
    assert 'id="btn-tts-toggle"' in html
    assert 'id="btn-settings"' in html
    assert 'id="shopping-list-container"' in html
    assert 'id="meal-container"' in html
    assert 'id="btn-clear-bought"' in html


def test_get_manifest_json():
    """Vérifie que le manifest Web App PWA est servi correctement."""
    response = client.get("/manifest.json")
    assert response.status_code == 200
    data = response.json()
    assert data["display"] == "standalone"
    assert "Assistant" in data["name"]
    assert "icons" in data
    assert data["start_url"] == "/app"


def test_get_service_worker():
    """Vérifie que le service worker PWA est accessible pour l'installation Android."""
    response = client.get("/sw.js")
    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    assert "javascript" in content_type or "text/" in content_type
    assert "CACHE_NAME" in response.text


def test_get_static_assets():
    """Vérifie que les assets statiques indispensables (CSS, JS, SVG) sont servis."""
    # CSS
    res_css = client.get("/static/style.css")
    assert res_css.status_code == 200
    assert "text/css" in res_css.headers.get("content-type", "")
    assert "--bg-main" in res_css.text

    # JS
    res_js = client.get("/static/app.js")
    assert res_js.status_code == 200
    assert "javascript" in res_js.headers.get("content-type", "")
    assert "SpeechRecognition" in res_js.text

    # SVG Icon
    res_svg = client.get("/static/icons/icon.svg")
    assert res_svg.status_code == 200
    assert "svg" in res_svg.headers.get("content-type", "")


def test_app_and_static_exempt_from_api_key(monkeypatch):
    """Les routes /app, /manifest.json, /sw.js et /static/* doivent être accessibles sans header X-API-Key

    car le navigateur les charge en direct. L'authentification protège les endpoints /api/v1/*.
    """
    monkeypatch.setattr(settings, "api_key", "super_secret_test_key")

    # /app doit rester accessible
    res_app = client.get("/app")
    assert res_app.status_code == 200

    # /manifest.json doit rester accessible
    res_manifest = client.get("/manifest.json")
    assert res_manifest.status_code == 200

    # /sw.js doit rester accessible
    res_sw = client.get("/sw.js")
    assert res_sw.status_code == 200

    # /static/style.css doit rester accessible
    res_css = client.get("/static/style.css")
    assert res_css.status_code == 200


def test_root_includes_pwa_link():
    """Vérifie que l'endpoint racine inclut le lien vers la PWA."""
    res = client.get("/")
    assert res.status_code == 200
    assert res.json().get("pwa") == "/app"
