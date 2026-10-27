"""Horloge applicative unique en fuseau Europe/Paris.

Le serveur (Cloud Run) tourne en UTC : « aujourd'hui » doit toujours être la date vécue
par l'utilisateur à Paris, y compris entre 00h et 02h.
"""
from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

APP_TIMEZONE = ZoneInfo("Europe/Paris")


def paris_now(now: Optional[datetime] = None) -> datetime:
    """Retourne l'instant courant (ou `now`, daté avec fuseau) exprimé à l'heure de Paris."""
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        raise ValueError(
            f"Datetime naïve refusée ({now.isoformat()}) : fournir un datetime avec fuseau "
            "(ex. datetime.now(timezone.utc)) pour éviter toute ambiguïté UTC/Paris."
        )
    return now.astimezone(APP_TIMEZONE)


def paris_today(now: Optional[datetime] = None) -> date:
    """Retourne la date du jour à Paris."""
    return paris_now(now).date()
