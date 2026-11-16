"""Événements Google Agenda des tâches avec heure (l'API Google Tasks ne garde que le jour de l'échéance).

Chaque événement est créé dans l'agenda principal et porte l'id de sa tâche dans ses propriétés privées
(`pahTask=1`, `pahTaskId`, `pahRappel`) : aucune table locale, un seul appel pour retrouver toutes les heures.
Lectures en cache (règle 8), invalidé à chaque écriture.
"""
import time
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel

from app.config import Settings
from app.connectors.calendar.calendar_connector import CALENDAR_API, CalendarAuthError, CalendarError
from app.connectors.google_oauth import LOGIN_SCRIPT, build_user_session
from app.connectors.google_rest import GoogleRestClient
from app.core.clock import APP_TIMEZONE, paris_now

EVENTS_URL = f"{CALENDAR_API}/calendars/primary/events"
PRIMARY_CALENDAR_URL = f"{CALENDAR_API}/users/me/calendarList/primary"
EVENT_DURATION = timedelta(minutes=30)
LOOKBACK = timedelta(days=60)  # événements passés encore utiles (tâches en retard)
MAX_OVERRIDES = 5  # limite Google des rappels personnalisés
LINK_PROPERTY = "pahTask"


class TaskEvent(BaseModel):
    task_id: str
    event_id: str
    debut: datetime
    rappel_minutes_avant: Optional[int] = None  # rappel ajouté à la demande, en plus de ceux de l'agenda


def task_start(day: date, hour: dt_time) -> datetime:
    return datetime.combine(day, hour, APP_TIMEZONE)


class TaskEventsConnector:
    def __init__(
        self, session: Any, ttl_seconds: int = 180, monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = paris_now,
    ) -> None:
        self._api = GoogleRestClient(session, "Google Agenda", CalendarError, CalendarAuthError)
        self._ttl_seconds = ttl_seconds
        self._monotonic = monotonic
        self._now = now
        self._cache: Optional[Tuple[float, Dict[str, TaskEvent]]] = None

    @classmethod
    def from_settings(cls, settings: Settings) -> "TaskEventsConnector":
        return cls(build_user_session(
            settings.google_oauth_client_id, settings.google_oauth_client_secret, settings.google_oauth_refresh_token,
        ))

    def list_task_events(self) -> Dict[str, TaskEvent]:
        """Événements liés à une tâche, par id de tâche (le plus récent l'emporte en cas de doublon)."""
        if self._cache and self._monotonic() - self._cache[0] < self._ttl_seconds:
            return self._cache[1]
        params = {
            "privateExtendedProperty": f"{LINK_PROPERTY}=1",
            "singleEvents": "true",
            "orderBy": "startTime",
            "timeMin": (self._now() - LOOKBACK).isoformat(),
            "maxResults": "250",
        }
        events: Dict[str, TaskEvent] = {}
        for item in self._api.paginate(EVENTS_URL, params, "en lisant les événements des tâches"):
            event = _to_task_event(item)
            if event:
                events[event.task_id] = event
        self._cache = (self._monotonic(), events)
        return events

    def create_event(
        self, task_id: str, titre: str, debut: datetime, rappel_minutes_avant: Optional[int],
    ) -> TaskEvent:
        if debut.tzinfo is None:
            raise ValueError(f"Début d'événement sans fuseau refusé ({debut.isoformat()}) : heure de Paris attendue.")
        start = debut.astimezone(APP_TIMEZONE)
        private = {LINK_PROPERTY: "1", "pahTaskId": task_id}
        if rappel_minutes_avant is None:
            reminders: Dict[str, Any] = {"useDefault": True}
        else:
            private["pahRappel"] = str(rappel_minutes_avant)
            reminders = {"useDefault": False, "overrides": self._overrides_with(rappel_minutes_avant)}
        body = {
            "summary": titre,
            "start": {"dateTime": start.isoformat(), "timeZone": "Europe/Paris"},
            "end": {"dateTime": (start + EVENT_DURATION).isoformat(), "timeZone": "Europe/Paris"},
            "reminders": reminders,
            "extendedProperties": {"private": private},
        }
        created = self._write("POST", EVENTS_URL, f"en créant l'événement « {titre} »", body)
        event = _to_task_event(created)
        if event is None:
            raise CalendarError(f"Événement « {titre} » créé sans lien vers sa tâche (réponse Google inattendue).")
        return event

    def delete_event(self, event_id: str) -> None:
        self._write("DELETE", f"{EVENTS_URL}/{event_id}", f"en supprimant l'événement {event_id}", None)

    def _overrides_with(self, minutes: int) -> List[Dict[str, Any]]:
        """Rappels par défaut de l'agenda principal + le rappel demandé (sans doublon, 5 au plus)."""
        primary = self._api.request("GET", PRIMARY_CALENDAR_URL, "en lisant les rappels par défaut de l'agenda")
        overrides = [dict(r) for r in primary.get("defaultReminders", [])]
        if not any(r.get("minutes") == minutes for r in overrides):
            overrides.append({"method": "popup", "minutes": minutes})
        return overrides[:MAX_OVERRIDES]

    def _write(self, method: str, url: str, action: str, body: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        try:
            result = self._api.request(method, url, action, json=body)
        except CalendarAuthError:
            raise
        except CalendarError as exc:
            if " 403 " in str(exc):
                raise CalendarError(
                    f"{exc} — droit d'écriture dans l'agenda manquant ? Relancer {LOGIN_SCRIPT} (droit "
                    "calendar.events), puis mettre à jour GOOGLE_OAUTH_REFRESH_TOKEN (.env et secret GitHub)."
                ) from exc
            raise
        finally:
            self._cache = None
        return result


def _to_task_event(item: Dict[str, Any]) -> Optional[TaskEvent]:
    private = (item.get("extendedProperties") or {}).get("private") or {}
    start = (item.get("start") or {}).get("dateTime")
    if not private.get("pahTaskId") or not start:
        return None
    rappel = private.get("pahRappel")
    return TaskEvent(
        task_id=private["pahTaskId"],
        event_id=item["id"],
        debut=datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(APP_TIMEZONE),
        rappel_minutes_avant=int(rappel) if rappel and rappel.isdigit() else None,
    )
