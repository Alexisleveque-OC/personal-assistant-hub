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
