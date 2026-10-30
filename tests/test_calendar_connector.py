"""Connecteur Google Agenda (Phase 8, étape 1) : agendas cochés, occurrences dépliées, fuseau Paris, cache 3 min."""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import pytest
from google.auth.exceptions import RefreshError

from app.connectors.calendar.calendar_connector import (
    CalendarAuthError,
    CalendarConnector,
    CalendarError,
)
from app.core.clock import APP_TIMEZONE

API = "https://www.googleapis.com/calendar/v3"


class FakeResponse:
    def __init__(self, payload: Dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> Dict[str, Any]:
        return self._payload


class FakeSession:
    """Simule `AuthorizedSession.get` : réponses par URL (liste = pages successives)."""

    def __init__(self, routes: Dict[str, Any]) -> None:
        self.routes = {url: list(r) if isinstance(r, list) else [r] for url, r in routes.items()}
        self.calls: List[Dict[str, Any]] = []

    def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> FakeResponse:
        self.calls.append({"url": url, "params": dict(params or {})})
        pages = self.routes[url]
        return pages.pop(0) if len(pages) > 1 else pages[0]


def calendars(*items: Dict[str, Any]) -> FakeResponse:
    return FakeResponse({"items": list(items)})


def events_url(calendar_id: str) -> str:
    from urllib.parse import quote
    return f"{API}/calendars/{quote(calendar_id, safe='')}/events"


PERSO = {"id": "perso-id", "summary": "Perso", "selected": True}
FAMILLE = {"id": "famille#id@group", "summary": "Famille", "summaryOverride": "Famille partagée", "selected": True}
MASQUE = {"id": "masque-id", "summary": "Masqué"}


def timed(summary: str, start: str, end: str, **extra: Any) -> Dict[str, Any]:
    return {"summary": summary, "start": {"dateTime": start}, "end": {"dateTime": end}, **extra}


def all_day(summary: str, start: str, end: str) -> Dict[str, Any]:
    return {"summary": summary, "start": {"date": start}, "end": {"date": end}}


def make_connector(perso_events, famille_events=(), **kwargs) -> tuple[CalendarConnector, FakeSession]:
    session = FakeSession({
        f"{API}/users/me/calendarList": calendars(PERSO, FAMILLE, MASQUE),
        events_url("perso-id"): FakeResponse({"items": list(perso_events)}),
        events_url("famille#id@group"): FakeResponse({"items": list(famille_events)}),
    })
    return CalendarConnector(session, **kwargs), session


def test_reads_only_the_calendars_checked_in_google_calendar():
    connector, session = make_connector([])
    connector.list_events(date(2026, 10, 30), date(2026, 10, 30))
    urls = [c["url"] for c in session.calls]
    assert events_url("perso-id") in urls
    assert events_url("famille#id@group") in urls
    assert events_url("masque-id") not in urls


def test_queries_the_whole_paris_days_with_recurring_events_expanded():
    connector, session = make_connector([])
    connector.list_events(date(2026, 10, 30), date(2026, 10, 31))
    params = next(c["params"] for c in session.calls if c["url"] == events_url("perso-id"))
    assert params["timeMin"] == "2026-10-30T00:00:00+01:00"
    assert params["timeMax"] == "2026-11-01T00:00:00+01:00"
    assert params["singleEvents"] == "true"
    assert params["orderBy"] == "startTime"
    assert params["timeZone"] == "Europe/Paris"


def test_maps_events_sorted_all_day_first_then_by_start_across_calendars():
    connector, _ = make_connector(
        [
            timed("Dentiste", "2026-10-30T14:00:00+01:00", "2026-10-30T14:30:00+01:00", location="Cabinet"),
            all_day("Vacances", "2026-10-30", "2026-11-02"),
        ],
        [timed("Réunion parents", "2026-10-30T08:30:00Z", "2026-10-30T09:30:00Z")],
    )
    events = connector.list_events(date(2026, 10, 30), date(2026, 10, 30))
    assert [e.titre for e in events] == ["Vacances", "Réunion parents", "Dentiste"]

    vacances, reunion, dentiste = events
    assert vacances.journee_entiere is True
    assert vacances.debut == datetime(2026, 10, 30, tzinfo=APP_TIMEZONE)
    assert vacances.fin == datetime(2026, 11, 2, tzinfo=APP_TIMEZONE)
    assert vacances.agenda == "Perso"
    assert reunion.agenda == "Famille partagée"
    assert reunion.debut == datetime(2026, 10, 30, 9, 30, tzinfo=APP_TIMEZONE)
    assert reunion.debut.utcoffset() == APP_TIMEZONE.utcoffset(datetime(2026, 10, 30))
    assert dentiste.lieu == "Cabinet"
    assert reunion.lieu is None


def test_events_of_several_days_are_sorted_day_by_day():
    connector, _ = make_connector([
        all_day("Férié", "2026-11-11", "2026-11-12"),
        timed("Coiffeur", "2026-11-07T10:00:00+01:00", "2026-11-07T11:00:00+01:00"),
        all_day("Déménagement", "2026-11-07", "2026-11-08"),
    ])
    events = connector.list_events(date(2026, 11, 7), date(2026, 11, 11))
    assert [e.titre for e in events] == ["Déménagement", "Coiffeur", "Férié"]


def test_event_without_title_is_named_busy():
    untitled = timed("", "2026-10-30T10:00:00+01:00", "2026-10-30T11:00:00+01:00")
    untitled.pop("summary")
    connector, _ = make_connector([untitled])
    assert connector.list_events(date(2026, 10, 30), date(2026, 10, 30))[0].titre == "Occupé"


def test_events_declined_by_the_user_are_skipped():
    declined = timed(
        "Afterwork", "2026-10-30T19:00:00+01:00", "2026-10-30T21:00:00+01:00",
        attendees=[{"self": True, "responseStatus": "declined"}, {"responseStatus": "accepted"}],
    )
    accepted = timed(
        "Point projet", "2026-10-30T10:00:00+01:00", "2026-10-30T11:00:00+01:00",
        attendees=[{"self": True, "responseStatus": "accepted"}],
    )
    connector, _ = make_connector([declined, accepted])
    assert [e.titre for e in connector.list_events(date(2026, 10, 30), date(2026, 10, 30))] == ["Point projet"]


def test_follows_pagination_of_events():
    session = FakeSession({
        f"{API}/users/me/calendarList": calendars(PERSO),
        events_url("perso-id"): [
            FakeResponse({"items": [timed("A", "2026-10-30T09:00:00+01:00", "2026-10-30T10:00:00+01:00")],
                          "nextPageToken": "p2"}),
            FakeResponse({"items": [timed("B", "2026-10-30T11:00:00+01:00", "2026-10-30T12:00:00+01:00")]}),
        ],
    })
    events = CalendarConnector(session).list_events(date(2026, 10, 30), date(2026, 10, 30))
    assert [e.titre for e in events] == ["A", "B"]
    assert session.calls[-1]["params"]["pageToken"] == "p2"


def test_same_period_is_served_from_cache_until_ttl_expires():
    clock = [1000.0]
    connector, session = make_connector([], ttl_seconds=180, monotonic=lambda: clock[0])
    connector.list_events(date(2026, 10, 30), date(2026, 10, 30))
    calls = len(session.calls)

    clock[0] += 179
    connector.list_events(date(2026, 10, 30), date(2026, 10, 30))
    assert len(session.calls) == calls

    connector.list_events(date(2026, 10, 31), date(2026, 10, 31))
    assert len(session.calls) > calls

    clock[0] += 2
    calls = len(session.calls)
    connector.list_events(date(2026, 10, 30), date(2026, 10, 30))
    assert len(session.calls) > calls


def test_end_before_start_is_refused():
    connector, _ = make_connector([])
    with pytest.raises(ValueError, match="31/10/2026.*30/10/2026"):
        connector.list_events(date(2026, 10, 31), date(2026, 10, 30))


def test_http_error_names_the_calendar_and_the_status():
    session = FakeSession({
        f"{API}/users/me/calendarList": calendars(FAMILLE),
        events_url("famille#id@group"): FakeResponse({"error": {"message": "Forbidden"}}, status_code=403),
    })
    with pytest.raises(CalendarError, match="403.*Famille partagée"):
        CalendarConnector(session).list_events(date(2026, 10, 30), date(2026, 10, 30))


class RevokedSession:
    def get(self, url, params=None):
        raise RefreshError("invalid_grant: Token has been expired or revoked.")


def test_revoked_token_tells_how_to_renew_it():
    with pytest.raises(CalendarAuthError) as exc:
        CalendarConnector(RevokedSession()).list_events(date(2026, 10, 30), date(2026, 10, 30))
    message = str(exc.value)
    assert "scripts/google_oauth_login.py" in message
    assert "GOOGLE_OAUTH_REFRESH_TOKEN" in message
    assert "invalid_grant" in message
    assert isinstance(exc.value, CalendarError)
