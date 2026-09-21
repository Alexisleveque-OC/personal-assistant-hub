"""Module de résolution des expressions temporelles et dates en français."""
from datetime import date, datetime, timedelta
import re
from typing import Optional
from pydantic import BaseModel, Field


class ResolvedDate(BaseModel):
    """Résultat de la résolution temporelle."""
    target_date: Optional[date] = None
    date_str: Optional[str] = None  # JJ/MM/AAAA
    day_name: Optional[str] = None  # Lundi, Mardi...
    period: Optional[str] = None    # "midi", "soir", "jour", "prochain"
    cleaned_query: str = Field(default="")


WEEKDAYS_FR = {
    "lundi": 0,
    "mardi": 1,
    "mercredi": 2,
    "jeudi": 3,
    "vendredi": 4,
    "samedi": 5,
    "dimanche": 6,
}

WEEKDAY_NAMES = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

MONTHS_FR = {
    "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "aout": 8, "août": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12,
}


def resolve_date_expression(text: str, now: Optional[datetime] = None) -> ResolvedDate:
    """Analyse une phrase en français et extrait la date cible et le moment de la journée."""
    ref_dt = now or datetime.now()
    today = ref_dt.date()
    cleaned = text.strip()
    lowered = cleaned.lower()

    # 1. Détection du moment (midi / soir / non précisé)
    period: Optional[str] = None
    if re.search(r"\bmidi\b", lowered):
        period = "midi"
    elif re.search(r"\bsoir\b", lowered):
        period = "soir"

    # 2. Détection "aujourd'hui" / "ce midi" / "ce soir"
    if re.search(r"\b(?:aujourd[' ]?hui|ce\s+midi|ce\s+soir)\b", lowered):
        p = period or "jour"
        # Nettoyer l'expression temporelle du texte
        query_clean = re.sub(r"\b(?:pour\s+)?(?:aujourd[' ]?hui|ce\s+midi|ce\s+soir)\b", "", cleaned, flags=re.IGNORECASE).strip()
        return ResolvedDate(
            target_date=today,
            date_str=today.strftime("%d/%m/%Y"),
            day_name=WEEKDAY_NAMES[today.weekday()],
            period=p,
            cleaned_query=query_clean,
        )

    # 3. Détection "demain"
    if re.search(r"\bdemain\b", lowered):
        target = today + timedelta(days=1)
        p = period or "demain"
        query_clean = re.sub(r"\b(?:pour\s+)?demain(?:\s+(?:midi|soir))?\b", "", cleaned, flags=re.IGNORECASE).strip()
        return ResolvedDate(
            target_date=target,
            date_str=target.strftime("%d/%m/%Y"),
            day_name=WEEKDAY_NAMES[target.weekday()],
            period=p,
            cleaned_query=query_clean,
        )

    # 4. Détection jour de la semaine ("jeudi", "jeudi prochain", "ce vendredi", etc.)
    weekday_pattern = r"\b(?:le\s+|ce\s+)?(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)(?:\s+prochain)?(?:\s+(?:midi|soir))?\b"
    weekday_match = re.search(weekday_pattern, lowered)
    if weekday_match:
        day_str = weekday_match.group(1)
        target_w = WEEKDAYS_FR[day_str]
        current_w = today.weekday()
        days_ahead = (target_w - current_w) % 7
        if days_ahead == 0 and "prochain" in weekday_match.group(0):
            days_ahead = 7
        elif days_ahead == 0:
            # Même jour mentionné
            days_ahead = 0
            
        target = today + timedelta(days=days_ahead)
        p = period or "jour"
        
        # Supprimer l'expression du texte pour isoler le plat (ex: "prévois du poulet pour jeudi" -> "prévois du poulet")
        full_match_text = weekday_match.group(0)
        query_clean = re.sub(rf"\b(?:pour\s+)?{re.escape(full_match_text)}\b", "", cleaned, flags=re.IGNORECASE).strip()
        return ResolvedDate(
            target_date=target,
            date_str=target.strftime("%d/%m/%Y"),
            day_name=WEEKDAY_NAMES[target.weekday()],
            period=p,
            cleaned_query=query_clean,
        )

    # 5. Détection date calendaire explicite ("le 24 septembre", "le 24/09", "le 24/09/2026")
    date_num_match = re.search(r"\b(?:le\s+)?(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", lowered)
    if date_num_match:
        day_val = int(date_num_match.group(1))
        month_val = int(date_num_match.group(2))
        year_str = date_num_match.group(3)
        year_val = int(year_str) if year_str else today.year
        if year_val < 100:
            year_val += 2000
        try:
            target = date(year_val, month_val, day_val)
            p = period or "jour"
            query_clean = re.sub(r"\b(?:pour\s+)?(?:le\s+)?\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", "", cleaned, flags=re.IGNORECASE).strip()
            return ResolvedDate(
                target_date=target,
                date_str=target.strftime("%d/%m/%Y"),
                day_name=WEEKDAY_NAMES[target.weekday()],
                period=p,
                cleaned_query=query_clean,
            )
        except ValueError:
            pass

    date_literal_match = re.search(
        r"\b(?:le\s+)?(\d{1,2})\s+(janvier|fevrier|février|mars|avril|mai|juin|juillet|aout|août|septembre|octobre|novembre|decembre|décembre)(?:\s+(\d{4}))?\b",
        lowered,
    )
    if date_literal_match:
        day_val = int(date_literal_match.group(1))
        month_name = date_literal_match.group(2)
        month_val = MONTHS_FR[month_name]
        year_val = int(date_literal_match.group(3)) if date_literal_match.group(3) else today.year
        try:
            target = date(year_val, month_val, day_val)
            p = period or "jour"
            query_clean = re.sub(
                r"\b(?:pour\s+)?(?:le\s+)?\d{1,2}\s+(?:janvier|fevrier|février|mars|avril|mai|juin|juillet|aout|août|septembre|octobre|novembre|decembre|décembre)(?:\s+\d{4})?\b",
                "",
                cleaned,
                flags=re.IGNORECASE,
            ).strip()
            return ResolvedDate(
                target_date=target,
                date_str=target.strftime("%d/%m/%Y"),
                day_name=WEEKDAY_NAMES[target.weekday()],
                period=p,
                cleaned_query=query_clean,
            )
        except ValueError:
            pass

    # 6. Aucun repère temporel spécifique trouvé
    # Si "midi" ou "soir" était mentionné seul ("ce midi", "ce soir" déjà pris en 2, mais au cas où "pour midi")
    if period:
        return ResolvedDate(
            target_date=today,
            date_str=today.strftime("%d/%m/%Y"),
            day_name=WEEKDAY_NAMES[today.weekday()],
            period=period,
            cleaned_query=cleaned,
        )

    return ResolvedDate(
        target_date=None,
        date_str=None,
        day_name=None,
        period="prochain",
        cleaned_query=cleaned,
    )
