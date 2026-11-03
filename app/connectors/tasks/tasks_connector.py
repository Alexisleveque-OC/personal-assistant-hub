"""Connecteur Google Tasks (API REST v1) : tâches non terminées de la liste par défaut « Mes tâches ».

Les lectures sont mises en cache (règle 8 : quotas et temps de réponse) ; toute écriture future devra appeler
`invalidate_cache`. Tâches avec échéance d'abord (date croissante), puis les autres dans l'ordre de la liste.
"""
import time
from datetime import date
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.config import Settings
from app.connectors.google_oauth import build_user_session
from app.connectors.google_rest import GoogleRestClient
from app.connectors.tasks.models import TaskItem

TASKS_API = "https://tasks.googleapis.com/tasks/v1"
DEFAULT_LIST_ID = "@default"
DEFAULT_LIST_NAME = "Mes tâches"
_TASKS_URL = f"{TASKS_API}/lists/{DEFAULT_LIST_ID}/tasks"


class TasksError(RuntimeError):
    """Échec explicite d'accès à Google Tasks (statut HTTP, liste concernée)."""


class TasksAuthError(TasksError):
    """Jeton de rafraîchissement refusé (révoqué ou expiré) : il faut refaire le consentement."""


class TasksConnector:
    def __init__(
        self, session: Any, ttl_seconds: int = 180, monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        """`session` : `AuthorizedSession` (ou doublure offrant `get(url, params=...)`)."""
        self._api = GoogleRestClient(session, "Google Tasks", TasksError, TasksAuthError)
        self._ttl_seconds = ttl_seconds
        self._monotonic = monotonic
        self._cache: Optional[Tuple[float, List[TaskItem]]] = None

    @classmethod
    def from_settings(cls, settings: Settings) -> "TasksConnector":
        return cls(build_user_session(
            settings.google_oauth_client_id, settings.google_oauth_client_secret, settings.google_oauth_refresh_token,
        ))

    def list_open_tasks(self) -> List[TaskItem]:
        if self._cache and self._monotonic() - self._cache[0] < self._ttl_seconds:
            return self._cache[1]
        items = self._api.paginate(
            _TASKS_URL,
            {"showCompleted": "false", "showHidden": "false", "maxResults": "100"},
            f"en lisant la liste « {DEFAULT_LIST_NAME} »",
        )
        tasks = [
            _to_task(item) for item in items
            if item.get("status") != "completed" and (item.get("title") or "").strip()
        ]
        tasks.sort(key=lambda t: (t.echeance is None, t.echeance or date.max))  # tri stable : ordre de la liste conservé
        self._cache = (self._monotonic(), tasks)
        return tasks

    def invalidate_cache(self) -> None:
        self._cache = None


def _to_task(item: Dict[str, Any]) -> TaskItem:
    due = item.get("due")
    return TaskItem(
        id=item["id"],
        titre=item["title"].strip(),
        echeance=date.fromisoformat(due[:10]) if due else None,  # « 2026-11-05T00:00:00.000Z » : seul le jour compte
        notes=item.get("notes") or None,
    )
