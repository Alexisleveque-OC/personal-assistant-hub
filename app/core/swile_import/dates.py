"""Dates des lignes Swile telles qu'affichées par l'appli, résolues par rapport au jour de l'import.

« Derniers paiements » : « mercredi 25 nov. 2026, 17:35 » ; accueil « Avantages » : « Aujourd'hui, … », « Hier, … »,
« lundi, … » (semaine écoulée), « 14 novembre, … » (année omise). Un paiement n'est jamais dans le futur ; une date
illisible donne None (la ligne est ignorée et signalée), jamais la date du jour par défaut.
"""
import re
import unicodedata
from datetime import date, timedelta
from typing import Optional

from app.core.date_resolver import WEEKDAYS_FR

_MONTHS = {
    "janv": 1, "fevr": 2, "fev": 2, "mars": 3, "avr": 4, "mai": 5, "juin": 6, "juil": 7, "aout": 8,
    "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
_RELATIVE_DAYS = {"aujourd'hui": 0, "hier": 1, "avant-hier": 2}
_DAY_MONTH = re.compile(r"\b(\d{1,2})\s+([a-z]+)\.?(?:\s+(\d{4}))?\b")


def _plain(text: str) -> str:
    """Minuscules sans accents, apostrophe typographique ramenée à « ' »."""
    stripped = unicodedata.normalize("NFKD", text.replace("’", "'")).encode("ascii", "ignore").decode()
    return stripped.lower().strip()


def _month(word: str) -> Optional[int]:
    return next((number for prefix, number in _MONTHS.items() if word.startswith(prefix)), None)


def parse_swile_date(raw: Optional[str], reference_date: date) -> Optional[date]:
    """Date du paiement, ou None si illisible ou future."""
    if not raw or not raw.strip():
        return None
    text = _plain(raw)

    match = _DAY_MONTH.search(text)
    if match and _month(match.group(2)):
        day, month = int(match.group(1)), _month(match.group(2))
        year = int(match.group(3)) if match.group(3) else reference_date.year
        try:
            found = date(year, month, day)
        except ValueError:
            return None
        if found > reference_date and not match.group(3):
            found = found.replace(year=year - 1)
        return None if found > reference_date else found

    head = text.split(",")[0].strip()
    if head in _RELATIVE_DAYS:
        return reference_date - timedelta(days=_RELATIVE_DAYS[head])
    if head in WEEKDAYS_FR:
        # « Aujourd'hui » désigne le jour même : un jour de semaine nommé est dans les 7 jours écoulés.
        return reference_date - timedelta(days=(reference_date.weekday() - WEEKDAYS_FR[head] - 1) % 7 + 1)
    return None
