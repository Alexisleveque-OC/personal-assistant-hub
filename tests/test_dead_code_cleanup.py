"""Refacto anti-tokens, lot 5 : suppression du code mort (jamais appelé hors des tests)."""
from pathlib import Path

from app.core.intent_parser import IntentParser
from app.core.models import IntentType

ROOT = Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_unused_api_helpers_are_removed():
    api = _read("app/static/js/api.js")
    assert "function patchSportSession(" not in api
    assert "function fetchSportSummariesData(" not in api
    assert "function patchSportSessionById(" in api


def test_unused_python_helpers_are_removed():
    assert "resolve_temporal_range" not in _read("app/core/date_resolver.py")
    assert "TemporalRange" not in _read("app/core/date_resolver.py")
    assert "get_morning_chronicle_snippet" not in _read("app/core/sport_gamification_service.py")


def test_second_brain_is_parsed_once_and_notes_listing_still_works():
    assert _read("app/core/intent_parser.py").count("self._parse_second_brain(") == 1
    parser = IntentParser()
    for query in ("liste mes notes", "quelles sont mes idées de dev", "liste mes bugs"):
        assert parser.parse(query).intent == IntentType.LIST_NOTES, query
