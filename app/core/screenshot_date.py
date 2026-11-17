"""Lecture résiliente de la date extraite d'une capture d'écran sportive (jamais dans le futur)."""
import re
from datetime import date, datetime, timedelta
from typing import Any, Optional

from app.core.date_resolver import WEEKDAYS_FR, resolve_date_expression


def parse_screenshot_date(raw_date: Any, reference_date: Optional[date] = None) -> date:
    """Résout de façon résiliente la date extraite d'une capture d'écran sportive.

    Règle fondamentale : une séance capturée s'est TOUJOURS déroulée dans le passé ou aujourd'hui,
    JAMAIS dans le futur.

    Supporte :
    - date ou datetime natif
    - Formats ISO : 'YYYY-MM-DD', 'YYYY-MM-DDTHH:MM:SS', 'YYYY-MM-DD HH:MM:SS'
    - Formats français complets : 'DD/MM/YYYY', 'DD/MM/YY', 'DD-MM-YYYY', 'DD.MM.YYYY'
    - Format jour/mois sans année : '14/10', '14/10 à 18:30', '14/10 - 18h30'
    - Formats textuels français : '08 oct. 2026', '8 oct 2026', '14 oct.', '14 octobre', 'Course à pied - 14 oct.'
    - Format 'Jour JJ' : 'Mercredi 14', 'Mardi 13', 'mercredi 14 oct'
    - Expressions relatives : 'hier', 'avant-hier', 'mercredi', 'mardi', 'dimanche dernier'
    - Repli propre sur reference_date (ou date.today()) si vide ou non résoluble.
    """
    ref_d = reference_date or date.today()
    if not raw_date:
        return ref_d

    if isinstance(raw_date, datetime):
        return raw_date.date()
    if isinstance(raw_date, date):
        return raw_date

    val = str(raw_date).strip()
    if not val:
        return ref_d

    # 1. ISO direct ou tronqué : YYYY-MM-DD (ex: 2026-10-12 ou 2026-10-12T12:55:00)
    iso_match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", val)
    if iso_match:
        try:
            return date(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
        except ValueError:
            pass

    # 2. Format numérique complet DD/MM/YYYY ou DD-MM-YYYY ou DD.MM.YYYY (ex: '12/10/2026 - 12:55')
    fr_full_match = re.search(r"\b(\d{1,2})[/\.-](\d{1,2})[/\.-](\d{2,4})\b", val)
    if fr_full_match:
        d = int(fr_full_match.group(1))
        m = int(fr_full_match.group(2))
        y = int(fr_full_match.group(3))
        if y < 100:
            y += 2000
        try:
            return date(y, m, d)
        except ValueError:
            pass

    # 3. Format numérique jour/mois sans année : DD/MM (ex: '14/10', '14/10 à 18:30', '14/10 - 18h30')
    fr_short_match = re.search(r"\b(\d{1,2})[/\.-](\d{1,2})\b", val)
    if fr_short_match:
        d = int(fr_short_match.group(1))
        m = int(fr_short_match.group(2))
        if 1 <= m <= 12 and 1 <= d <= 31:
            try:
                target = date(ref_d.year, m, d)
                if target > ref_d:
                    target = date(ref_d.year - 1, m, d)
                return target
            except ValueError:
                pass

    # 4. Format 'Jour JJ' (ex: 'Mercredi 14', 'Mardi 13', 'mercredi 14 oct')
    jour_jj_match = re.search(
        r"\b(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+(\d{1,2})\b",
        val,
        re.IGNORECASE,
    )
    if jour_jj_match:
        day_num = int(jour_jj_match.group(2))
        weekday_target = WEEKDAYS_FR[jour_jj_match.group(1).lower()]
        if 1 <= day_num <= 31:
            # Tester le mois courant
            try:
                cand = date(ref_d.year, ref_d.month, day_num)
                if cand.weekday() == weekday_target and cand <= ref_d:
                    return cand
            except ValueError:
                pass
            # Tester le mois précédent si le jour dépasse le jour de référence
            prev_month = ref_d.month - 1 if ref_d.month > 1 else 12
            prev_year = ref_d.year if ref_d.month > 1 else ref_d.year - 1
            try:
                cand = date(prev_year, prev_month, day_num)
                if cand.weekday() == weekday_target:
                    return cand
            except ValueError:
                pass

    # 5. Format textuel avec nom ou abréviation de mois français (ex: '08 oct. 2026', '8 octobre', '14 oct.', 'Course à pied - 14 oct.')
    text_month_match = re.search(
        r"\b(\d{1,2})\s+([a-zA-ZÀ-ÿ\.]+)(?:\s+(\d{4}))?",
        val,
        re.IGNORECASE,
    )
    if text_month_match:
        d = int(text_month_match.group(1))
        raw_m = text_month_match.group(2).lower().strip(". ")
        month_map = {
            "jan": 1, "janv": 1, "janvier": 1,
            "fev": 2, "fév": 2, "fevr": 2, "févr": 2, "fevrier": 2, "février": 2,
            "mar": 3, "mars": 3,
            "avr": 4, "avril": 4,
            "mai": 5,
            "jui": 6, "juin": 6,
            "juil": 7, "juillet": 7,
            "aou": 8, "aoû": 8, "aout": 8, "août": 8,
            "sep": 9, "sept": 9, "septembre": 9,
            "oct": 10, "octobre": 10,
            "nov": 11, "novembre": 11,
            "dec": 12, "déc": 12, "decembre": 12, "décembre": 12,
        }
        month_num = month_map.get(raw_m) or month_map.get(raw_m[:3])
        if month_num and 1 <= d <= 31:
            y = int(text_month_match.group(3)) if text_month_match.group(3) else ref_d.year
            try:
                target = date(y, month_num, d)
                if not text_month_match.group(3) and target > ref_d:
                    target = date(ref_d.year - 1, month_num, d)
                return target
            except ValueError:
                pass

    # 6. Jour de la semaine isolé (ex: 'mercredi', 'mardi', 'dimanche')
    weekday_match = re.search(r"\b(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\b", val, re.IGNORECASE)
    if weekday_match:
        target_wd = WEEKDAYS_FR[weekday_match.group(1).lower()]
        delta = (ref_d.weekday() - target_wd) % 7
        if delta == 0:
            # Même jour de la semaine : si ce n'est pas explicitement 'aujourd'hui', il s'agit d'aujourd'hui
            return ref_d
        return ref_d - timedelta(days=delta)

    # 7. Expressions relatives via resolve_date_expression ('hier', 'avant-hier', etc.)
    ref_dt = datetime.combine(ref_d, datetime.min.time())
    resolved = resolve_date_expression(val, now=ref_dt)
    if resolved and resolved.target_date:
        res_d = resolved.target_date
        # Toujours garantir que le résultat ne pointe pas vers le futur pour une capture d'écran sportive
        if res_d > ref_d:
            res_d = res_d - timedelta(days=7)
        return res_d

    return ref_d


