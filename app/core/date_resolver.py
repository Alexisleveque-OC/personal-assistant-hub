"""Module de résolution des expressions temporelles et dates en français."""
from datetime import date, datetime, timedelta
import re
from typing import Optional, Union, Any
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

MONTH_NAMES_FR = {
    1: "janvier", 2: "février", 3: "mars", 4: "avril",
    5: "mai", 6: "juin", 7: "juillet", 8: "août",
    9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre",
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

    # 4. Détection date calendaire explicite avec nom de mois ("dimanche 20 septembre", "le 24 septembre", "20 sept")
    month_names_pattern = "|".join(MONTHS_FR.keys())
    date_literal_pattern = (
        rf"\b(?:(?:le\s+|ce\s+)?(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+)?"
        rf"(?:le\s+)?(\d{{1,2}})\s+({month_names_pattern})(?:\s+(\d{{4}}))?(?:\s+(?:midi|soir))?\b"
    )
    date_literal_match = re.search(date_literal_pattern, lowered)
    if date_literal_match:
        day_val = int(date_literal_match.group(1))
        month_name = date_literal_match.group(2)
        month_val = MONTHS_FR[month_name]
        year_val = int(date_literal_match.group(3)) if date_literal_match.group(3) else today.year
        try:
            target = date(year_val, month_val, day_val)
            p = period or "jour"
            query_clean = re.sub(
                rf"\b(?:pour\s+)?{re.escape(date_literal_match.group(0))}\b",
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

    # 5. Détection date numérique ("dimanche 20/09", "le 24/09", "le 24/09/2026")
    date_num_pattern = (
        r"\b(?:(?:le\s+|ce\s+)?(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+)?"
        r"(?:le\s+)?(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?(?:\s+(?:midi|soir))?\b"
    )
    date_num_match = re.search(date_num_pattern, lowered)
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
            query_clean = re.sub(
                rf"\b(?:pour\s+)?{re.escape(date_num_match.group(0))}\b",
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

    # 6. Détection jour de la semaine seul ("jeudi", "jeudi prochain", "ce vendredi", etc.)
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


def parse_target_date(
    target: Union[str, date, datetime, None],
    period: Optional[str] = None,
    default: Optional[date] = None,
) -> date:
    """Résout de manière robuste et sûre une date cible à partir de divers formats.

    Gère :
    - Instance de date ou datetime
    - Mots-clés temporels : 'today', 'tomorrow', 'yesterday', 'ce soir', 'ce midi', 'aujourd'hui', 'demain', 'hier'
    - Formats de chaînes : JJ/MM/AAAA, AAAA-MM-JJ, JJ-MM-AAAA, JJ/MM, ISO 8601
    - Résolution basée sur 'period' si target est None ou indéterminé
    - Fallback garanti sans exception ValueError (renvoie default ou date.today()).
    """
    today = date.today()

    if target is None or target == "":
        if period:
            p_lower = period.strip().lower()
            if "demain" in p_lower:
                return today + timedelta(days=1)
            elif "hier" in p_lower:
                return today - timedelta(days=1)
        return default or today

    if isinstance(target, datetime):
        return target.date()

    if isinstance(target, date):
        return target

    if not isinstance(target, str):
        return default or today

    raw = target.strip()
    s = raw.lower()

    # 1. Mots-clés directs
    if s in ("today", "ce soir", "ce midi", "aujourd'hui", "aujourdhui", "ce jour", "current_date", "now"):
        return today
    if s in ("tomorrow", "demain", "lendemain"):
        return today + timedelta(days=1)
    if s in ("yesterday", "hier", "veille"):
        return today - timedelta(days=1)

    # 2. Formats explicites courants
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass

    # 3. Format jour/mois sans année (ex: 15/10 ou 15-10)
    for fmt in ("%d/%m", "%d-%m"):
        try:
            d_part = datetime.strptime(raw, fmt).date()
            return date(today.year, d_part.month, d_part.day)
        except ValueError:
            pass

    # 4. Format ISO avec heure éventuelle (ex: 2026-10-02T12:00:00)
    try:
        return date.fromisoformat(raw[:10])
    except (ValueError, TypeError):
        pass

    # 5. Tentative via le parseur d'expression en français (ex: "jeudi 24 octobre")
    try:
        res = resolve_date_expression(raw)
        if res.target_date:
            return res.target_date
    except Exception:
        pass

    # 6. Fallback final respectant period si présent
    if period and "demain" in period.strip().lower():
        return today + timedelta(days=1)

    return default or today


def format_natural_spoken_date(
    target_date: date,
    reference_date: Optional[date] = None,
    preposition: bool = True,
) -> str:
    """Formate une date en français naturel et oralisé.

    Exemples :
    - aujourd'hui / d'aujourd'hui
    - demain / de demain
    - après-demain / d'après-demain
    - hier / d'hier
    - avant-hier / d'avant-hier
    - mardi 6 octobre / du mardi 6 octobre
    - lundi 6 octobre 2025 / du lundi 6 octobre 2025
    """
    ref = reference_date or date.today()
    delta_days = (target_date - ref).days

    if delta_days == 0:
        return "d'aujourd'hui" if preposition else "aujourd'hui"
    elif delta_days == 1:
        return "de demain" if preposition else "demain"
    elif delta_days == 2:
        return "d'après-demain" if preposition else "après-demain"
    elif delta_days == -1:
        return "d'hier" if preposition else "hier"
    elif delta_days == -2:
        return "d'avant-hier" if preposition else "avant-hier"

    weekday_str = WEEKDAY_NAMES[target_date.weekday()].lower()
    month_str = MONTH_NAMES_FR.get(target_date.month, "")
    year_suffix = f" {target_date.year}" if target_date.year != ref.year else ""

    date_label = f"{weekday_str} {target_date.day} {month_str}{year_suffix}"
    if preposition:
        return f"du {date_label}"
    return date_label

