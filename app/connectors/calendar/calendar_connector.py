"""Connecteur Google Agenda (lecture seule, API REST v3) : agendas cochés par l'utilisateur, fuseau Paris.

Les occurrences des événements récurrents sont dépliées par l'API (`singleEvents`). Les lectures sont
mises en cache par période (règle 8 : quotas et temps de réponse) ; l'agenda n'est jamais modifié ici.
"""
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, Iterator, List, Tuple
from urllib.parse import quote

from google.auth.exceptions import RefreshError

from app.config import Settings
from app.connectors.calendar.models import CalendarEvent
from app.connectors.google_oauth import LOGIN_SCRIPT, build_user_session
from app.core.clock import APP_TIMEZONE

CALENDAR_API = "https://www.googleapis.com/calendar/v3"
UNTITLED_EVENT = "Occupé"  # agenda partagé en « disponibilités uniquement » : pas de titre
# Agenda technique de Google : exposé « coché » par l'API mais absent de la liste des agendas de l'utilisateur.
WEEK_NUMBERS_SUFFIX = "#weeknum@group.v.calendar.google.com"


class CalendarError(RuntimeError):
    """Échec explicite de lecture de l'Agenda Google (statut HTTP, agenda concerné)."""


class CalendarAuthError(CalendarError):
    """Jeton de rafraîchissement refusé (révoqué ou expiré) : il faut refaire le consentement."""


class CalendarConnector:
    def __init__(
        self, session: Any, ttl_seconds: int = 180, monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        """`session` : `AuthorizedSession` (ou doublure offrant `get(url, params=...)`)."""
        self._session = session
        self._ttl_seconds = ttl_seconds
        self._monotonic = monotonic
        self._cache: Dict[Tuple[date, date], Tuple[float, List[CalendarEvent]]] = {}

    @classmethod
    def from_settings(cls, settings: Settings) -> "CalendarConnector":
        return cls(build_user_session(
            settings.google_oauth_client_id, settings.google_oauth_client_secret, settings.google_oauth_refresh_token,
        ))

    def list_events(self, start: date, end: date) -> List[CalendarEvent]:
        """Événements des jours `start` à `end` inclus, jour par jour : journées entières d'abord, puis par heure."""
        if end < start:
            raise ValueError(f"Période inversée : début {start:%d/%m/%Y} après fin {end:%d/%m/%Y}.")
        key = (start, end)
        cached = self._cache.get(key)
        if cached and self._monotonic() - cached[0] < self._ttl_seconds:
            return cached[1]

        time_min = datetime.combine(start, datetime.min.time(), APP_TIMEZONE)
        time_max = datetime.combine(end + timedelta(days=1), datetime.min.time(), APP_TIMEZONE)
        events = [
            event
            for calendar_id, name in self._selected_calendars()
            for event in self._calendar_events(calendar_id, name, time_min, time_max)
        ]
        events.sort(key=lambda e: (e.debut.date(), not e.journee_entiere, e.debut, e.agenda, e.titre))
        self._cache[key] = (self._monotonic(), events)
        return events

    def _selected_calendars(self) -> List[Tuple[str, str]]:
        items = self._paginate(f"{CALENDAR_API}/users/me/calendarList", {}, "la liste des agendas")
        return [
            (item["id"], item.get("summaryOverride") or item.get("summary") or item["id"])
            for item in items if item.get("selected") and not item["id"].endswith(WEEK_NUMBERS_SUFFIX)
        ]

    def _calendar_events(
        self, calendar_id: str, name: str, time_min: datetime, time_max: datetime,
    ) -> Iterator[CalendarEvent]:
        params = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "timeZone": "Europe/Paris",
            "maxResults": "250",
        }
        url = f"{CALENDAR_API}/calendars/{quote(calendar_id, safe='')}/events"
        for item in self._paginate(url, params, f"l'agenda « {name} »"):
            if _declined_by_user(item):
                continue
            yield _to_event(item, name)

    def _paginate(self, url: str, params: Dict[str, str], resource: str) -> Iterator[Dict[str, Any]]:
        page_params = dict(params)
        while True:
            payload = self._get(url, page_params, resource)
            yield from payload.get("items", [])
            token = payload.get("nextPageToken")
            if not token:
                return
            page_params = {**params, "pageToken": token}

    def _get(self, url: str, params: Dict[str, str], resource: str) -> Dict[str, Any]:
        try:
            response = self._session.get(url, params=params)
        except RefreshError as exc:
            raise CalendarAuthError(
                f"Jeton Google refusé (révoqué ou expiré) en lisant {resource} : relancer {LOGIN_SCRIPT}, puis mettre "
                f"à jour GOOGLE_OAUTH_REFRESH_TOKEN (.env et secret GitHub). Détail : {exc}"
            ) from exc
        if response.status_code != 200:
            raise CalendarError(
                f"API Google Agenda : HTTP {response.status_code} en lisant {resource} : {response.text[:300]}"
            )
        return response.json()


def _declined_by_user(item: Dict[str, Any]) -> bool:
    return any(a.get("self") and a.get("responseStatus") == "declined" for a in item.get("attendees", []))


def _to_event(item: Dict[str, Any], calendar_name: str) -> CalendarEvent:
    all_day = "date" in item["start"]
    return CalendarEvent(
        titre=item.get("summary") or UNTITLED_EVENT,
        agenda=calendar_name,
        journee_entiere=all_day,
        debut=_parse_bound(item["start"]),
        fin=_parse_bound(item["end"]),
        lieu=item.get("location") or None,
    )


def _parse_bound(bound: Dict[str, str]) -> datetime:
    if "date" in bound:
        return datetime.combine(date.fromisoformat(bound["date"]), datetime.min.time(), APP_TIMEZONE)
    return datetime.fromisoformat(bound["dateTime"].replace("Z", "+00:00")).astimezone(APP_TIMEZONE)
