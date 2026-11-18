"""Règles globales du front : rendu par le DOM (pas d'innerHTML), jamais d'alert() bloquant."""
import re

from tests.js_helpers import STATIC

# Modules antérieurs à la refonte qui écrivent encore du HTML (gabarits fixes, sans donnée utilisateur).
INNER_HTML_ALLOWED = {"tts.js", "offline_outbox.js", "screenshot_import.js"}


def _js_files():
    return [STATIC / "app.js", *sorted((STATIC / "js").rglob("*.js"))]


def test_inner_html_is_never_used_outside_the_known_legacy_modules():
    users = {p.name for p in _js_files() if "innerHTML" in p.read_text(encoding="utf-8")}
    assert users <= INNER_HTML_ALLOWED, users - INNER_HTML_ALLOWED


def test_no_blocking_alert():
    code = re.compile(r"^(?!\s*//).*\balert\(", re.M)  # hors lignes de commentaire
    offenders = [p.name for p in _js_files() if code.search(p.read_text(encoding="utf-8"))]
    assert offenders == []
