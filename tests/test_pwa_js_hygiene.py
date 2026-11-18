"""Règles globales du front : rendu par le DOM (pas d'innerHTML) dans les vues, jamais d'alert() bloquant."""
import re

from tests.js_helpers import STATIC


def _js_files(folder):
    return sorted(folder.rglob("*.js"))


def test_views_never_use_inner_html():
    offenders = [p.name for p in _js_files(STATIC / "js" / "views") if "innerHTML" in p.read_text(encoding="utf-8")]
    assert offenders == []


def test_no_blocking_alert():
    code = re.compile(r"^(?!\s*//).*\balert\(", re.M)  # hors lignes de commentaire
    offenders = [p.name for p in [STATIC / "app.js", *_js_files(STATIC / "js")] if code.search(p.read_text(encoding="utf-8"))]
    assert offenders == []
