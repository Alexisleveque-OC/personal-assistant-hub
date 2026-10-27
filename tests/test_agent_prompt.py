"""Tests du prompt système de l'agent."""
from datetime import date

from app.connectors.sheets.sport_models import SportSessionStatus, SportSessionType
from app.core.agent.prompt import build_system_prompt
from app.core.agent.tools.sport_models import SessionView


def _view(session_id: int, day: date, type_seance: SportSessionType) -> SessionView:
    return SessionView(id=session_id, date=day, jour="x", statut=SportSessionStatus.REALISE, type_seance=type_seance)


def test_prompt_contains_paris_date_and_sessions_with_ids():
    prompt = build_system_prompt(date(2026, 10, 26), [_view(7, date(2026, 10, 25), SportSessionType.EF)])
    assert "lundi 26/10/2026" in prompt and "dimanche 25/10/2026" in prompt
    assert "id=7" in prompt


def test_prompt_flags_days_with_several_sessions():
    prompt = build_system_prompt(date(2026, 10, 26), [
        _view(2, date(2026, 10, 25), SportSessionType.EF),
        _view(1, date(2026, 10, 25), SportSessionType.RENFORCEMENT),
        _view(3, date(2026, 10, 24), SportSessionType.EF),
    ])
    assert "dimanche 25/10/2026 : 2 séances (EF, Renforcement)" in prompt
    assert "samedi 24/10/2026 : " not in prompt


def test_prompt_without_ambiguous_day_has_no_warning_section():
    prompt = build_system_prompt(date(2026, 10, 26), [_view(3, date(2026, 10, 24), SportSessionType.EF)])
    assert "plusieurs séances" not in prompt.split("Séances récentes")[1]


def test_prompt_has_shopping_meals_and_note_rules():
    prompt = build_system_prompt(date(2026, 10, 26), [])
    rules = prompt.split("Aujourd'hui :")[0]
    assert "Courses et repas" in rules
    assert "rayon_a_demander" in rules and "hors_carnet_confirme" in rules
    assert "ne les mentionne pas" in rules  # la question de l'application suit : pas de doublon
    assert "get_recipe" in rules and "add_shopping_items" in rules
    assert "toujours en français" in rules


def test_sessions_sharing_a_day_are_flagged_on_their_own_line():
    prompt = build_system_prompt(date(2026, 10, 26), [
        _view(2, date(2026, 10, 25), SportSessionType.EF),
        _view(1, date(2026, 10, 25), SportSessionType.RENFORCEMENT),
        _view(3, date(2026, 10, 24), SportSessionType.EF),
    ])
    lines = {line.split(" | ")[0]: line for line in prompt.splitlines() if line.startswith("- id=")}
    assert "AMBIGU" in lines["- id=2"] and "AMBIGU" in lines["- id=1"]
    assert "AMBIGU" not in lines["- id=3"]
