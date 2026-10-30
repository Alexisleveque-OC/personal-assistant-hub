"""Identifiants OAuth de l'utilisateur Google (Agenda, Tasks, puis Gmail) : un seul jeton de rafraîchissement.

Le compte de service reste réservé à Sheets : Tasks n'est pas accessible à un compte de service
pour un compte @gmail.com, et l'Agenda lu ainsi couvre tous les agendas affichés par l'utilisateur.
"""
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials

GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_USER_SCOPES = (
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/tasks",
)
LOGIN_SCRIPT = "scripts/google_oauth_login.py"


class GoogleOAuthNotConfiguredError(RuntimeError):
    """Réglage OAuth manquant : le message liste les variables à renseigner et la marche à suivre."""


def build_user_session(client_id: str, client_secret: str, refresh_token: str) -> AuthorizedSession:
    """Session HTTP authentifiée ; le jeton d'accès est obtenu (et renouvelé) au premier appel, pas ici."""
    missing = [
        name for name, value in (
            ("GOOGLE_OAUTH_CLIENT_ID", client_id),
            ("GOOGLE_OAUTH_CLIENT_SECRET", client_secret),
            ("GOOGLE_OAUTH_REFRESH_TOKEN", refresh_token),
        )
        if not value.strip()
    ]
    if missing:
        raise GoogleOAuthNotConfiguredError(
            f"Réglages OAuth Google manquants : {', '.join(missing)}. Renseigner l'ID et le secret du client OAuth "
            f"dans .env, puis lancer {LOGIN_SCRIPT} pour obtenir le jeton de rafraîchissement."
        )
    # Pas de scopes imposés au rafraîchissement : le jeton porte ceux accordés lors du consentement.
    credentials = Credentials(
        token=None,
        refresh_token=refresh_token.strip(),
        client_id=client_id.strip(),
        client_secret=client_secret.strip(),
        token_uri=GOOGLE_TOKEN_URI,
    )
    return AuthorizedSession(credentials)
