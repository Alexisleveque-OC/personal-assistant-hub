"""Outils Agenda de l'agent : lecture de l'Agenda Google via `CalendarConnector`, jour par jour (heure de Paris)."""
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Protocol

from app.connectors.calendar.calendar_connector import CalendarError
from app.connectors.calendar.models import CalendarEvent
from app.core.agent.tools.calendar_models import AgendaDay, AgendaEvent, AgendaView, GetAgendaArgs
from app.core.agent.tools.sport_models import WEEKDAYS_FR
from app.core.agent.tools.tool_error import ToolError

MAX_AGENDA_DAYS = 14


class CalendarReader(Protocol):
    def list_events(self, start: date, end: date) -> List[CalendarEvent]: ...


class CalendarToolError(ToolError):
    """Erreur Agenda renvoyée telle quelle au modèle."""


class CalendarTools:
    def __init__(self, connector: Optional[CalendarReader], unavailable_reason: str = "") -> None:
        """`unavailable_reason` : cause de l'absence de connecteur (réglage OAuth manquant…), dite à l'utilisateur."""
        self._connector = connector
        self._unavailable_reason = unavailable_reason

    @property
    def connector(self) -> CalendarReader:
        if self._connector is None:
            raise CalendarToolError(f"L'Agenda Google est indisponible : {self._unavailable_reason or 'non configuré'}.")
        return self._connector

    def get_agenda(self, args: GetAgendaArgs) -> AgendaView:
        start = args.date_debut
        end = args.date_fin or start
        if end < start:
            raise CalendarToolError(f"date_fin ({end}) est antérieure à date_debut ({start}).")
        if (end - start).days + 1 > MAX_AGENDA_DAYS:
            raise CalendarToolError(f"Période trop longue : {MAX_AGENDA_DAYS} jours maximum ({start} → {end}).")
        try:
            events = self.connector.list_events(start, end)
        except CalendarError as exc:
            raise CalendarToolError(str(exc)) from exc

        days: Dict[date, List[AgendaEvent]] = {
            start + timedelta(days=offset): [] for offset in range((end - start).days + 1)
        }
        for event in events:
            for day in _days_shown(event, start, end):
                days[day].append(_to_view(event, day))
        return AgendaView(jours=[
            AgendaDay(date=day, jour=WEEKDAYS_FR[day.weekday()], evenements=evenements)
            for day, evenements in days.items()
        ])


def _days_shown(event: CalendarEvent, start: date, end: date) -> List[date]:
    """Journée entière : chaque jour couvert (fin exclusive) ; sinon le jour de début, ou le 1er jour s'il est antérieur."""
    if not event.journee_entiere:
        return [max(event.debut.date(), start)]
    first = max(event.debut.date(), start)
    last = min(event.fin.date() - timedelta(days=1), end)
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


def _to_view(event: CalendarEvent, day: date) -> AgendaEvent:
    if event.journee_entiere:
        return AgendaEvent(titre=event.titre, journee_entiere=True, lieu=event.lieu, agenda=event.agenda)
    return AgendaEvent(
        titre=event.titre,
        journee_entiere=False,
        heure_debut=_hour(event.debut, day),
        heure_fin=_hour(event.fin, day),
        lieu=event.lieu,
        agenda=event.agenda,
    )


def _hour(moment: datetime, day: date) -> str:
    if moment.date() < day:
        return f"{moment:%H:%M} (la veille)"
    if moment.date() > day:
        return f"{moment:%H:%M} (le lendemain)"
    return f"{moment:%H:%M}"
