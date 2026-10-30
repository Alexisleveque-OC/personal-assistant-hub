"""Consentement OAuth Google en local (Agenda, Tasks) : écrit GOOGLE_OAUTH_REFRESH_TOKEN dans .env, sans l'afficher.

Prérequis : GOOGLE_OAUTH_CLIENT_ID et GOOGLE_OAUTH_CLIENT_SECRET (client « Application de bureau ») dans .env,
et `pip install google-auth-oauthlib` (outil local, absent de l'image de production).

Usage (WSL) : .venv/bin/python scripts/google_oauth_login.py
Ouvrir l'adresse affichée dans le navigateur Windows, accepter, puis reporter le jeton de .env
dans le secret GitHub GOOGLE_OAUTH_REFRESH_TOKEN.
"""
from pathlib import Path
import re
import sys

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
REFRESH_TOKEN_KEY = "GOOGLE_OAUTH_REFRESH_TOKEN"
LOCAL_PORT = 8765


def upsert_env_var(content: str, key: str, value: str) -> str:
    """Remplace (clé insensible à la casse) ou ajoute `key=value`, en conservant les fins de ligne du fichier."""
    newline = "\r\n" if "\r\n" in content else "\n"
    pattern = re.compile(rf"^{re.escape(key)}=.*?(\r?)$", re.IGNORECASE | re.MULTILINE)
    if pattern.search(content):
        return pattern.sub(lambda m: f"{key}={value}{m.group(1)}", content, count=1)
    if content and not content.endswith("\n"):
        content += newline
    return f"{content}{key}={value}{newline}"


def main() -> int:
    sys.path.insert(0, str(ENV_FILE.parent))
    from app.config import settings
    from app.connectors.google_oauth import GOOGLE_TOKEN_URI, GOOGLE_USER_SCOPES

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from oauthlib.oauth2.rfc6749.errors import MismatchingStateError
    except ImportError:
        print("Module manquant : lancer `.venv/bin/pip install google-auth-oauthlib`.", file=sys.stderr)
        return 1
    if not settings.google_oauth_client_id.strip() or not settings.google_oauth_client_secret.strip():
        print("GOOGLE_OAUTH_CLIENT_ID et GOOGLE_OAUTH_CLIENT_SECRET doivent être renseignés dans .env.", file=sys.stderr)
        return 1

    flow = InstalledAppFlow.from_client_config(
        {"installed": {
            "client_id": settings.google_oauth_client_id.strip(),
            "client_secret": settings.google_oauth_client_secret.strip(),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": GOOGLE_TOKEN_URI,
            "redirect_uris": ["http://localhost"],
        }},
        scopes=list(GOOGLE_USER_SCOPES),
    )
    # prompt=consent : Google ne renvoie un jeton de rafraîchissement qu'à un consentement explicite.
    # bind_addr 0.0.0.0 : le navigateur Windows doit joindre le serveur de retour lancé dans WSL.
    try:
        credentials = flow.run_local_server(
            port=LOCAL_PORT, bind_addr="0.0.0.0", open_browser=False, prompt="consent", access_type="offline",
            authorization_prompt_message="Ouvrir cette adresse dans le navigateur et accepter :\n{url}\n",
            success_message="Consentement reçu, vous pouvez fermer cet onglet.",
        )
    except MismatchingStateError:
        print("Réponse d'une tentative précédente (state différent) : fermer les anciens onglets Google/localhost, "
              "relancer le script et n'ouvrir que la nouvelle adresse affichée.", file=sys.stderr)
        return 1
    if not credentials.refresh_token:
        print("Aucun jeton de rafraîchissement reçu : révoquer l'accès sur "
              "https://myaccount.google.com/permissions puis relancer.", file=sys.stderr)
        return 1

    ENV_FILE.write_text(
        upsert_env_var(ENV_FILE.read_text(encoding="utf-8"), REFRESH_TOKEN_KEY, credentials.refresh_token),
        encoding="utf-8", newline="",
    )
    print(f"{REFRESH_TOKEN_KEY} enregistré dans {ENV_FILE.name} (non affiché). "
          "Reporter sa valeur dans le secret GitHub du même nom.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
