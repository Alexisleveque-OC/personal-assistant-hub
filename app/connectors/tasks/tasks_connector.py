"""Connecteur Google Tasks (API REST v1) : tâches non terminées de la liste par défaut « Mes tâches ».

Les lectures sont mises en cache (règle 8 : quotas et temps de réponse) ; toute écriture future devra appeler
`invalidate_cache`. Tâches avec échéance d'abord (date croissante), puis les autres dans l'ordre de la liste.
"""
import time
from datetime import date
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from google.auth.exceptions import RefreshError

from app.config import Settings
from app.connectors.google_oauth import LOGIN_SCRIPT, build_user_session
from app.connectors.tasks.models import TaskItem

TASKS_API = "https://tasks.googleapis.com/tasks/v1"
DEFAULT_LIST_ID = "@default"
DEFAULT_LIST_NAME = "Mes tâches"


class TasksError(RuntimeError):
    """Échec explicite d'accès à Google Tasks (statut HTTP, liste concernée)."""


class TasksAuthError(TasksError):
    """Jeton de rafraîchissement refusé (révoqué ou expiré) : il faut refaire le consentement."""


class TasksConnector:
    def __init__(
        self, session: Any, ttl_seconds: int = 180, monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        """`session` : `AuthorizedSession` (ou doublure offrant `get(url, params=...)`)."""
        self._session = session
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
        items = self._paginate(
            f"{TASKS_API}/lists/{DEFAULT_LIST_ID}/tasks",
            {"showCompleted": "false", "showHidden": "false", "maxResults": "100"},
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

    def _paginate(self, url: str, params: Dict[str, str]) -> Iterator[Dict[str, Any]]:
        page_params = dict(params)
        while True:
            payload = self._get(url, page_params)
            yield from payload.get("items", [])
            token = payload.get("nextPageToken")
            if not token:
                return
            page_params = {**params, "pageToken": token}

    def _get(self, url: str, params: Dict[str, str]) -> Dict[str, Any]:
        resource = f"la liste « {DEFAULT_LIST_NAME} »"
        try:
            response = self._session.get(url, params=params)
        except RefreshError as exc:
            raise TasksAuthError(
                f"Jeton Google refusé (révoqué ou expiré) en lisant {resource} : relancer {LOGIN_SCRIPT}, puis mettre "
                f"à jour GOOGLE_OAUTH_REFRESH_TOKEN (.env et secret GitHub). Détail : {exc}"
            ) from exc
        if response.status_code != 200:
            raise TasksError(f"API Google Tasks : HTTP {response.status_code} en lisant {resource} : {response.text[:300]}")
        return response.json()


def _to_task(item: Dict[str, Any]) -> TaskItem:
    due = item.get("due")
    return TaskItem(
        id=item["id"],
        titre=item["title"].strip(),
        echeance=date.fromisoformat(due[:10]) if due else None,  # « 2026-11-05T00:00:00.000Z » : seul le jour compte
        notes=item.get("notes") or None,
    )
