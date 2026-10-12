"""Module de résolution des expressions temporelles et dates en français."""
from datetime import date, datetime, timedelta
import re
from enum import Enum
from typing import List, Optional, Union, Any
from pydantic import BaseModel, Field


class ResolvedDate(BaseModel):
    """Résultat de la résolution temporelle."""
    target_date: Optional[date] = None
    date_str: Optional[str] = None  # JJ/MM/AAAA
    day_name: Optional[str] = None  # Lundi, Mardi...
    period: Optional[str] = None    # "midi", "soir", "jour", "prochain", "hier", "demain"...
    cleaned_query: str = Field(default="")


class TemporalRangeType(str, Enum):
    """Types de plages temporelles relatives."""
    DAYS_WINDOW = "days_window"
    CURRENT_WEEK = "current_week"
    LAST_WEEK = "last_week"
    NEXT_WEEK = "next_week"


class TemporalRangeResult(BaseModel):
    """Résultat d'une plage temporelle relative."""
    range_type: TemporalRangeType
    start_date: date
    end_date: date
    all_dates: List[date]
    nb_days: int
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


def resolve_temporal_range(text: str, now: Optional[datetime] = None) -> Optional[TemporalRangeResult]:
    """Extrait une plage temporelle relative ('ces 3 derniers jours', 'cette semaine', 'la semaine dernière')."""
    ref_dt = now or datetime.now()
    today = ref_dt.date()
    cleaned = text.strip()
    lowered = cleaned.lower()

    # Protection étanche : exclure les décomptes conversationnels ("ces 3 derniers échanges/messages")
    if re.search(r"\b(?:échanges?|echanges?|messages?|phrases?|discussions?|tours?)\b", lowered):
        return None

    # 1. Fenêtre de N derniers jours ("ces 3 derniers jours", "les 5 derniers jours")
    days_window_match = re.search(r"\b(?:ces|les|sur\s+les|depuis)\s+(\d+)\s+derniers?\s+jours?\b", lowered)
    if days_window_match:
        nb_days = int(days_window_match.group(1))
        if nb_days > 0:
            start_d = today - timedelta(days=nb_days - 1)
            end_d = today
            all_dates = [start_d + timedelta(days=i) for i in range(nb_days)]
            query_clean = re.sub(re.escape(days_window_match.group(0)), "", cleaned, flags=re.IGNORECASE).strip()
            return TemporalRangeResult(
                range_type=TemporalRangeType.DAYS_WINDOW,
                start_date=start_d,
                end_date=end_d,
                all_dates=all_dates,
                nb_days=nb_days,
                cleaned_query=query_clean,
            )

    # 2. "cette semaine"
    if re.search(r"\b(?:cette\s+semaine|semaine\s+en\s+cours)\b", lowered):
        start_d = today - timedelta(days=today.weekday())
        end_d = start_d + timedelta(days=6)
        all_dates = [start_d + timedelta(days=i) for i in range(7)]
        query_clean = re.sub(r"\b(?:cette\s+semaine|semaine\s+en\s+cours)\b", "", cleaned, flags=re.IGNORECASE).strip()
        return TemporalRangeResult(
            range_type=TemporalRangeType.CURRENT_WEEK,
            start_date=start_d,
            end_date=end_d,
            all_dates=all_dates,
            nb_days=7,
            cleaned_query=query_clean,
        )

    # 3. "la semaine dernière" / "semaine passée"
    if re.search(r"\b(?:la\s+)?semaine\s+(?:dernière|derniere|passée|passee)\b", lowered):
        current_monday = today - timedelta(days=today.weekday())
        start_d = current_monday - timedelta(days=7)
        end_d = start_d + timedelta(days=6)
        all_dates = [start_d + timedelta(days=i) for i in range(7)]
        query_clean = re.sub(r"\b(?:la\s+)?semaine\s+(?:dernière|derniere|passée|passee)\b", "", cleaned, flags=re.IGNORECASE).strip()
        return TemporalRangeResult(
            range_type=TemporalRangeType.LAST_WEEK,
            start_date=start_d,
            end_date=end_d,
            all_dates=all_dates,
            nb_days=7,
            cleaned_query=query_clean,
        )

    # 4. "la semaine prochaine"
    if re.search(r"\b(?:la\s+)?semaine\s+prochaine\b", lowered):
        current_monday = today - timedelta(days=today.weekday())
        start_d = current_monday + timedelta(days=7)
        end_d = start_d + timedelta(days=6)
        all_dates = [start_d + timedelta(days=i) for i in range(7)]
        query_clean = re.sub(r"\b(?:la\s+)?semaine\s+prochaine\b", "", cleaned, flags=re.IGNORECASE).strip()
        return TemporalRangeResult(
            range_type=TemporalRangeType.NEXT_WEEK,
            start_date=start_d,
            end_date=end_d,
            all_dates=all_dates,
            nb_days=7,
            cleaned_query=query_clean,
        )

    return None


def resolve_date_expression(text: str, now: Optional[datetime] = None) -> ResolvedDate:
    """Analyse une phrase en français et extrait la date cible et le moment de la journée."""
    ref_dt = now or datetime.now()
    today = ref_dt.date()
    cleaned = text.strip()
    lowered = cleaned.lower()

    # Protection étanche : exclure les décomptes d'échanges conversationnels purs
    if re.search(r"\b(?:échanges?|echanges?|messages?|phrases?|discussions?|tours?)\b", lowered) and not re.search(
        r"\b(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|hier|demain|aujourd[' ]?hui)\b", lowered
    ):
        return ResolvedDate(cleaned_query=cleaned)

    # 1. Détection du moment (midi / soir / non précisé)
    period: Optional[str] = None
    if re.search(r"\bmidi\b", lowered):
        period = "midi"
    elif re.search(r"\bsoir\b", lowered):
        period = "soir"

    # 2. Détection "avant-hier" / "l'avant-veille" (prioritaire sur "hier")
    if re.search(r"\b(?:avant[- ]hier|l[' ]avant[- ]veille)\b", lowered):
        target = today - timedelta(days=2)
        p = period or "avant-hier"
        query_clean = re.sub(r"\b(?:pour\s+|d[' ]?)?(?:avant[- ]hier|l[' ]avant[- ]veille)(?:\s+(?:midi|soir))?\b", "", cleaned, flags=re.IGNORECASE).strip()
        return ResolvedDate(
            target_date=target,
            date_str=target.strftime("%d/%m/%Y"),
            day_name=WEEKDAY_NAMES[target.weekday()],
            period=p,
            cleaned_query=query_clean,
        )

    # 3. Détection "hier" / "la veille"
    if re.search(r"\b(?:hier|la\s+veille)\b", lowered):
        target = today - timedelta(days=1)
        p = period or "hier"
        query_clean = re.sub(r"\b(?:pour\s+|d[' ]?)?(?:hier|la\s+veille)(?:\s+(?:midi|soir))?\b", "", cleaned, flags=re.IGNORECASE).strip()
        return ResolvedDate(
            target_date=target,
            date_str=target.strftime("%d/%m/%Y"),
            day_name=WEEKDAY_NAMES[target.weekday()],
            period=p,
            cleaned_query=query_clean,
        )

    # 4. Détection "après-demain" / "le surlendemain" (prioritaire sur "demain")
    if re.search(r"\b(?:après[- ]demain|apres[- ]demain|le\s+surlendemain)\b", lowered):
        target = today + timedelta(days=2)
        p = period or "après-demain"
        query_clean = re.sub(r"\b(?:pour\s+|d[' ]?)?(?:après[- ]demain|apres[- ]demain|le\s+surlendemain)(?:\s+(?:midi|soir))?\b", "", cleaned, flags=re.IGNORECASE).strip()
        return ResolvedDate(
            target_date=target,
            date_str=target.strftime("%d/%m/%Y"),
            day_name=WEEKDAY_NAMES[target.weekday()],
            period=p,
            cleaned_query=query_clean,
        )

    # 5. Détection "aujourd'hui" / "ce midi" / "ce soir"
    if re.search(r"\b(?:aujourd[' ]?hui|ce\s+midi|ce\s+soir)\b", lowered):
        p = period or "jour"
        query_clean = re.sub(r"\b(?:pour\s+|d[' ]?)?(?:aujourd[' ]?hui|ce\s+midi|ce\s+soir)\b", "", cleaned, flags=re.IGNORECASE).strip()
        return ResolvedDate(
            target_date=today,
            date_str=today.strftime("%d/%m/%Y"),
            day_name=WEEKDAY_NAMES[today.weekday()],
            period=p,
            cleaned_query=query_clean,
        )

    # 6. Détection "demain" / "le lendemain"
    if re.search(r"\b(?:demain|le\s+lendemain)\b", lowered):
        target = today + timedelta(days=1)
        p = period or "demain"
        query_clean = re.sub(r"\b(?:pour\s+|de\s+)?(?:demain|le\s+lendemain)(?:\s+(?:midi|soir))?\b", "", cleaned, flags=re.IGNORECASE).strip()
        return ResolvedDate(
            target_date=target,
            date_str=target.strftime("%d/%m/%Y"),
            day_name=WEEKDAY_NAMES[target.weekday()],
            period=p,
            cleaned_query=query_clean,
        )

    # 7. Détection jour de la semaine avec "dernier" / "dernière" (ex: "dimanche dernier", "lundi dernier")
    weekday_last_pattern = r"\b(?:le\s+|ce\s+|de\s+)?(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+(?:dernier|dernière|derniere)\b"
    weekday_last_match = re.search(weekday_last_pattern, lowered)
    if weekday_last_match:
        day_str = weekday_last_match.group(1)
        target_w = WEEKDAYS_FR[day_str]
        current_w = today.weekday()
        days_back = (current_w - target_w) % 7
        if days_back == 0:
            days_back = 7  # Si on est lundi et qu'on dit "lundi dernier", c'est il y a 7 jours
        target = today - timedelta(days=days_back)
        p = period or "passé"
        query_clean = re.sub(rf"\b(?:pour\s+|de\s+)?{re.escape(weekday_last_match.group(0))}\b", "", cleaned, flags=re.IGNORECASE).strip()
        return ResolvedDate(
            target_date=target,
            date_str=target.strftime("%d/%m/%Y"),
            day_name=WEEKDAY_NAMES[target.weekday()],
            period=p,
            cleaned_query=query_clean,
        )

    # 8. Détection date calendaire explicite avec nom de mois ("dimanche 20 septembre", "le 24 septembre", "20 sept")
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

    # 9. Détection date numérique ("dimanche 20/09", "le 24/09", "le 24/09/2026")
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

    # 10. Détection jour de la semaine seul ("jeudi", "jeudi prochain", "ce vendredi", etc.)
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
            days_ahead = 0

        target = today + timedelta(days=days_ahead)
        p = period or "jour"
        full_match_text = weekday_match.group(0)
        query_clean = re.sub(rf"\b(?:pour\s+)?{re.escape(full_match_text)}\b", "", cleaned, flags=re.IGNORECASE).strip()
        return ResolvedDate(
            target_date=target,
            date_str=target.strftime("%d/%m/%Y"),
            day_name=WEEKDAY_NAMES[target.weekday()],
            period=p,
            cleaned_query=query_clean,
        )

    # 11. Moment seul (midi / soir)
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
    if s in ("yesterday", "hier", "veille", "la veille"):
        return today - timedelta(days=1)
    if s in ("avant-hier", "avanthier", "l'avant-veille", "avant veille"):
        return today - timedelta(days=2)
    if s in ("après-demain", "apres-demain", "surlendemain", "le surlendemain"):
        return today + timedelta(days=2)

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

