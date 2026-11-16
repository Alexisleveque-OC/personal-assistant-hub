"""Événements Google Agenda liés aux tâches (tâche avec heure) : lecture, création, suppression, cache."""
from datetime import datetime, time

import pytest

from app.connectors.calendar.calendar_connector import CalendarError
from app.connectors.calendar.task_events import TaskEventsConnector
from app.core.clock import APP_TIMEZONE
from tests.test_calendar_connector import FakeResponse
from tests.test_tasks_connector import WritableSession

EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
PRIMARY_URL = "https://www.googleapis.com/calendar/v3/users/me/calendarList/primary"
NOW = datetime(2026, 11, 16, 9, 0, tzinfo=APP_TIMEZONE)


def linked_event(task_id: str, start: str, event_id: str = "", rappel: str = "") -> dict:
    private = {"pahTask": "1", "pahTaskId": task_id}
    if rappel:
        private["pahRappel"] = rappel
    return {
        "id": event_id or f"ev-{task_id}",
        "start": {"dateTime": start, "timeZone": "Europe/Paris"},
        "extendedProperties": {"private": private},
    }


def make(*events: dict, writes=(), primary=None, **kwargs):
    routes = {EVENTS_URL: FakeResponse({"items": list(events)})}
    if primary is not None:
        routes[PRIMARY_URL] = FakeResponse(primary)
    session = WritableSession(routes, writes)
    return TaskEventsConnector(session, now=lambda: NOW, **kwargs), session


def test_lists_only_the_events_linked_to_a_task_by_task_id():
    connector, session = make(linked_event("t1", "2026-11-19T14:30:00+01:00", rappel="1440"))
    events = connector.list_task_events()
    params = session.calls[0]["params"]
    assert session.calls[0]["url"] == EVENTS_URL
    assert params["privateExtendedProperty"] == "pahTask=1"
    assert params["singleEvents"] == "true"
    event = events["t1"]
    assert (event.event_id, event.debut, event.rappel_minutes_avant) == (
        "ev-t1", datetime(2026, 11, 19, 14, 30, tzinfo=APP_TIMEZONE), 1440,
    )


def test_events_are_cached_until_a_write():
    connector, session = make(writes=[FakeResponse({}, 204)])
    connector.list_task_events()
    connector.list_task_events()
    assert len(session.calls) == 1
    connector.delete_event("ev-1")
    connector.list_task_events()
    assert len(session.calls) == 2


def test_creates_a_30_minute_event_with_the_default_reminders():
    created = linked_event("t1", "2026-11-19T14:30:00+01:00")
    connector, session = make(writes=[FakeResponse(created)])
    event = connector.create_event("t1", "ORL", datetime(2026, 11, 19, 14, 30, tzinfo=APP_TIMEZONE), None)
    call = session.write_calls[0]
    assert (call["method"], call["url"]) == ("POST", EVENTS_URL)
    body = call["json"]
    assert body["summary"] == "ORL"
    assert body["start"] == {"dateTime": "2026-11-19T14:30:00+01:00", "timeZone": "Europe/Paris"}
    assert body["end"] == {"dateTime": "2026-11-19T15:00:00+01:00", "timeZone": "Europe/Paris"}
    assert body["reminders"] == {"useDefault": True}
    assert body["extendedProperties"] == {"private": {"pahTask": "1", "pahTaskId": "t1"}}
    assert event.event_id == "ev-t1"


def test_an_extra_reminder_is_added_to_the_calendar_default_ones():
    created = linked_event("t1", "2026-11-19T14:30:00+01:00", rappel="1440")
    primary = {"id": "primary", "defaultReminders": [{"method": "popup", "minutes": 10}]}
    connector, session = make(writes=[FakeResponse(created)], primary=primary)
    event = connector.create_event("t1", "ORL", datetime(2026, 11, 19, 14, 30, tzinfo=APP_TIMEZONE), 1440)
    body = session.write_calls[0]["json"]
    assert body["reminders"] == {
        "useDefault": False,
        "overrides": [{"method": "popup", "minutes": 10}, {"method": "popup", "minutes": 1440}],
    }
    assert body["extendedProperties"]["private"]["pahRappel"] == "1440"
    assert event.rappel_minutes_avant == 1440


def test_an_extra_reminder_equal_to_a_default_one_is_not_duplicated():
    created = linked_event("t1", "2026-11-19T14:30:00+01:00", rappel="10")
    primary = {"defaultReminders": [{"method": "popup", "minutes": 10}]}
    connector, session = make(writes=[FakeResponse(created)], primary=primary)
    connector.create_event("t1", "ORL", datetime(2026, 11, 19, 14, 30, tzinfo=APP_TIMEZONE), 10)
    assert session.write_calls[0]["json"]["reminders"]["overrides"] == [{"method": "popup", "minutes": 10}]


def test_naive_start_is_refused():
    connector, _ = make()
    with pytest.raises(ValueError, match="fuseau"):
        connector.create_event("t1", "ORL", datetime(2026, 11, 19, 14, 30), None)


def test_deletes_an_event():
    connector, session = make(writes=[FakeResponse({}, 204)])
    connector.delete_event("ev-1")
    assert (session.write_calls[0]["method"], session.write_calls[0]["url"]) == ("DELETE", f"{EVENTS_URL}/ev-1")


def test_missing_write_permission_says_how_to_grant_it():
    connector, _ = make(writes=[FakeResponse({"error": "insufficientPermissions"}, 403)])
    with pytest.raises(CalendarError) as exc:
        connector.create_event("t1", "ORL", datetime(2026, 11, 19, 14, 30, tzinfo=APP_TIMEZONE), None)
    assert "403" in str(exc.value)
    assert "google_oauth_login.py" in str(exc.value)


def test_start_time_helper():
    from app.connectors.calendar.task_events import task_start
    from datetime import date
    assert task_start(date(2026, 11, 19), time(14, 30)) == datetime(2026, 11, 19, 14, 30, tzinfo=APP_TIMEZONE)
