"""Page de confidentialité publique exigée par l'écran de consentement OAuth Google (Phase 8)."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_privacy_page_is_public_html():
    res = client.get("/static/privacy.html")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")


def test_privacy_page_states_read_scope_and_no_sharing():
    html = client.get("/static/privacy.html").text
    assert "Google Agenda" in html
    assert "Google Tasks" in html
    assert "aucun tiers" in html
    assert "myaccount.google.com/permissions" in html
