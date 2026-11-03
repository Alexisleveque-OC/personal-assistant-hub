"""Appels REST aux API Google utilisateur (Agenda, Tasks) : statut vérifié, pagination, jeton refusé expliqué.

Chaque connecteur fournit ses propres classes d'erreur pour que l'appelant sache quelle API a échoué.
"""
from typing import Any, Dict, Iterator, Optional

from google.auth.exceptions import RefreshError

from app.connectors.google_oauth import LOGIN_SCRIPT


class GoogleRestClient:
    def __init__(
        self, session: Any, api_label: str, error_cls: type[Exception], auth_error_cls: type[Exception],
    ) -> None:
        """`session` : `AuthorizedSession` (ou doublure offrant `request(method, url, ...)` / `get`)."""
        self._session = session
        self._api_label = api_label
        self._error_cls = error_cls
        self._auth_error_cls = auth_error_cls

    def request(
        self, method: str, url: str, action: str,
        params: Optional[Dict[str, str]] = None, json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """`action` décrit l'opération pour les messages d'erreur (« en lisant la liste « Mes tâches » »)."""
        try:
            if method == "GET":
                response = self._session.get(url, params=params)
            else:
                response = self._session.request(method, url, params=params, json=json)
        except RefreshError as exc:
            raise self._auth_error_cls(
                f"Jeton Google refusé (révoqué ou expiré) {action} : relancer {LOGIN_SCRIPT}, puis mettre "
                f"à jour GOOGLE_OAUTH_REFRESH_TOKEN (.env et secret GitHub). Détail : {exc}"
            ) from exc
        if response.status_code not in (200, 204):
            raise self._error_cls(f"API {self._api_label} : HTTP {response.status_code} {action} : {response.text[:300]}")
        return response.json() if response.status_code == 200 else {}

    def paginate(self, url: str, params: Dict[str, str], action: str) -> Iterator[Dict[str, Any]]:
        page_params = dict(params)
        while True:
            payload = self.request("GET", url, action, params=page_params)
            yield from payload.get("items", [])
            token = payload.get("nextPageToken")
            if not token:
                return
            page_params = {**params, "pageToken": token}
