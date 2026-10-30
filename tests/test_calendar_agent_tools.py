"""Outil agent `get_agenda` (Phase 8, étape 1) : jours groupés, horizon de 14 jours, erreurs explicites."""
from datetime import date, datetime
from typing import List, Optional

import pytest

from app.connectors.calendar.calendar_connector import CalendarError
from app.connectors.calendar.models import CalendarEvent
from app.core.agent.prompt import build_system_prompt
from app.core.agent.tool_registry import ToolRegistry
from app.core.agent.tools.calendar_models import GetAgendaArgs
from app.core.agent.tools.calendar_registry import calendar_tool_definitions
from app.core.agent.tools.calendar_tools import CalendarTools
from app.core.agent.tools.tool_error import ToolError
from app.core.clock import APP_TIMEZONE


def paris(*args: int) -> datetime:
    return datetime(*args, tzinfo=APP_TIMEZONE)


class FakeCalendar:
    def __init__(self, events: List[CalendarEvent], error: Optional[Exception] = None) -> None:
        self.events = events
        self.error = error
        self.calls: List[tuple] = []

    def list_events(self, start: date, end: date) -> List[CalendarEvent]:
        self.calls.append((start, end))
        if self.error:
            raise self.error
        return self.events


VACANCES = CalendarEvent(
    titre="Vacances", agenda="Perso", journee_entiere=True, debut=paris(2026, 10, 29), fin=paris(2026, 11, 1),
)
DENTISTE = CalendarEvent(
    titre="Dentiste", agenda="Perso", journee_entiere=False, lieu="Cabinet",
    debut=paris(2026, 10, 30, 14, 0), fin=paris(2026, 10, 30, 14, 30),
)
VEILLE_TARD = CalendarEvent(
    titre="Soirée", agenda="Famille", journee_entiere=False, debut=paris(2026, 10, 29, 22, 0), fin=paris(2026, 10, 30, 1, 0),
)


def test_single_day_by_default_with_events_and_hours():
    calendar = FakeCalendar([VACANCES, DENTISTE])
    view = CalendarTools(calendar).get_agenda(GetAgendaArgs(date_debut=date(2026, 10, 30)))
    assert calendar.calls == [(date(2026, 10, 30), date(2026, 10, 30))]
    assert len(view.jours) == 1
    day = view.jours[0]
    assert (day.date, day.jour) == (date(2026, 10, 30), "vendredi")
    assert [(e.titre, e.journee_entiere, e.heure_debut, e.heure_fin, e.lieu, e.agenda) for e in day.evenements] == [
        ("Vacances", True, None, None, None, "Perso"),
        ("Dentiste", False, "14:00", "14:30", "Cabinet", "Perso"),
    ]


def test_every_day_of_the_period_is_listed_even_when_empty():
    view = CalendarTools(FakeCalendar([DENTISTE])).get_agenda(
        GetAgendaArgs(date_debut=date(2026, 10, 30), date_fin=date(2026, 11, 2)),
    )
    assert [(d.date.day, len(d.evenements)) for d in view.jours] == [(30, 1), (31, 0), (1, 0), (2, 0)]


def test_multi_day_all_day_event_appears_on_each_covered_day_of_the_period():
    view = CalendarTools(FakeCalendar([VACANCES])).get_agenda(
        GetAgendaArgs(date_debut=date(2026, 10, 30), date_fin=date(2026, 11, 1)),
    )
    # fin exclusive (01/11 à minuit) : le 1er novembre n'est plus en vacances
    assert [[e.titre for e in d.evenements] for d in view.jours] == [["Vacances"], ["Vacances"], []]


def test_event_started_before_the_period_is_shown_on_its_first_day():
    view = CalendarTools(FakeCalendar([VEILLE_TARD])).get_agenda(GetAgendaArgs(date_debut=date(2026, 10, 30)))
    assert [e.titre for e in view.jours[0].evenements] == ["Soirée"]
    assert view.jours[0].evenements[0].heure_debut == "22:00 (la veille)"


def test_more_than_fourteen_days_is_refused():
    with pytest.raises(ToolError, match="14 jours"):
        CalendarTools(FakeCalendar([])).get_agenda(
            GetAgendaArgs(date_debut=date(2026, 10, 30), date_fin=date(2026, 11, 13)),
        )


def test_end_before_start_is_refused():
    with pytest.raises(ToolError, match="date_fin"):
        CalendarTools(FakeCalendar([])).get_agenda(
            GetAgendaArgs(date_debut=date(2026, 10, 30), date_fin=date(2026, 10, 29)),
        )


def test_unconfigured_calendar_gives_the_reason():
    tools = CalendarTools(None, unavailable_reason="Réglages OAuth Google manquants : GOOGLE_OAUTH_REFRESH_TOKEN")
    with pytest.raises(ToolError, match="Agenda.*GOOGLE_OAUTH_REFRESH_TOKEN"):
        tools.get_agenda(GetAgendaArgs(date_debut=date(2026, 10, 30)))


def test_calendar_errors_are_passed_to_the_model_as_is():
    tools = CalendarTools(FakeCalendar([], error=CalendarError("HTTP 403 sur l'agenda « Famille »")))
    with pytest.raises(ToolError, match="403.*Famille"):
        tools.get_agenda(GetAgendaArgs(date_debut=date(2026, 10, 30)))


@pytest.mark.asyncio
async def test_registry_exposes_get_agenda_with_its_dates():
    registry = ToolRegistry(calendar_tool_definitions(CalendarTools(FakeCalendar([DENTISTE]))))
    declaration = next(d for d in registry.declarations() if d["name"] == "get_agenda")
    assert set(declaration["parameters"]["properties"]) == {"date_debut", "date_fin"}

    execution = await registry.execute("get_agenda", {"date_debut": "2026-10-30"})
    assert execution.error is None
    assert execution.response["jours"][0]["evenements"][0]["titre"] == "Dentiste"


def test_prompt_tells_how_to_read_the_agenda_aloud():
    prompt = build_system_prompt(date(2026, 10, 30), [])
    assert "get_agenda" in prompt
    assert "Rien de prévu" in prompt
