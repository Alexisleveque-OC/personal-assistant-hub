"""Identifiants OAuth de l'utilisateur Google (Phase 8) : un seul jeton de rafraîchissement pour Agenda et Tasks."""
import pytest
from google.auth.transport.requests import AuthorizedSession

from app.connectors.google_oauth import (
    GOOGLE_USER_SCOPES,
    GoogleOAuthNotConfiguredError,
    build_user_session,
)


def test_builds_an_authorized_session_without_any_network_call():
    session = build_user_session(client_id="id", client_secret="secret", refresh_token="refresh")
    assert isinstance(session, AuthorizedSession)
    assert session.credentials.refresh_token == "refresh"
    assert session.credentials.token_uri == "https://oauth2.googleapis.com/token"


def test_missing_settings_are_all_named_with_the_action_to_take():
    with pytest.raises(GoogleOAuthNotConfiguredError) as exc:
        build_user_session(client_id="id", client_secret=" ", refresh_token="")
    message = str(exc.value)
    assert "GOOGLE_OAUTH_CLIENT_SECRET" in message
    assert "GOOGLE_OAUTH_REFRESH_TOKEN" in message
    assert "GOOGLE_OAUTH_CLIENT_ID" not in message
    assert "scripts/google_oauth_login.py" in message


def test_scopes_are_read_only_calendar_and_tasks():
    assert GOOGLE_USER_SCOPES == (
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/tasks",
    )
