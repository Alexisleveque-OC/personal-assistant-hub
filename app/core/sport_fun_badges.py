"""Trophées pop-culture et secrets ajoutés le 16/11 (ROADMAP Étape 3) : fonctions pures, sans état.

Seuils calibrés sur les données réelles (218 séances au 16/11) pour qu'environ un quart tombe d'office.
Univers : Astérix / Mission Cléopâtre, World of Warcraft (serveurs EU : reset du mercredi), Seigneur des Anneaux,
Brandon Sanderson sans spoiler (Roshar, Fils-des-Brumes ère 1, Warbreaker ; rien d'Elantris ni de l'ère 2).
"""
from collections import Counter
from datetime import date as dt_date
from datetime import timedelta
from typing import Iterable, List, Optional

from app.connectors.sheets.sport_models import (
    BadgeCategory,
    SportBadge,
    SportSession,
    SportSessionStatus,
    SportSessionType,
)

SLOW_PACE_SEC_PER_KM = 450  # 7:30 /km
ROLLING_WINDOW_DAYS = 91  # « 3 mois glissants »
LOTR_45_LEAGUES_KM = 217.0


# ---------- Mesures sur l'historique ----------

def _remarks(session: SportSession) -> str:
    return (session.remarques or "").lower()


def _any_keyword(realised: Iterable[SportSession], keywords: Iterable[str]) -> bool:
    words = list(keywords)
    return any(any(w in _remarks(s) for w in words) for s in realised)


def _count_type(realised: List[SportSession], session_type: SportSessionType) -> int:
    return sum(1 for s in realised if s.type_seance == session_type)


def _max_in_window(realised: List[SportSession], days: int, value=lambda s: 1) -> float:
    """Plus grand total de `value` sur une fenêtre glissante de `days` jours (bornes incluses)."""
    ordered = sorted(realised, key=lambda s: s.date)
    best = 0.0
    start = 0
    total = 0.0
    for end, session in enumerate(ordered):
        total += value(session)
        while (session.date - ordered[start].date).days >= days:
            total -= value(ordered[start])
            start += 1
        best = max(best, total)
    return best


def _best_week_streak(realised: List[SportSession], min_per_week: int) -> int:
    """Plus longue suite de semaines ISO consécutives comptant au moins `min_per_week` séances."""
    per_week = Counter(s.date - timedelta(days=s.date.weekday()) for s in realised)
    mondays = sorted(m for m, n in per_week.items() if n >= min_per_week)
    best = current = 0
    previous: Optional[dt_date] = None
    for monday in mondays:
        current = current + 1 if previous and monday - previous == timedelta(days=7) else 1
        best = max(best, current)
        previous = monday
    return best


def _longest_break_days(realised: List[SportSession]) -> int:
    days = sorted({s.date for s in realised})
    return max((b - a).days for a, b in zip(days, days[1:])) if len(days) > 1 else 0


def _longest_run_records_beaten(realised: List[SportSession]) -> int:
    """Nombre de fois où la plus longue sortie a été battue (la première séance ne compte pas)."""
    beaten = 0
    longest = 0.0
    for session in sorted(realised, key=lambda s: s.date):
        distance = session.distance_km or 0.0
        if distance > longest:
            beaten += longest > 0
            longest = distance
    return beaten


def _max_sessions_in_a_month(realised: List[SportSession]) -> int:
    per_month = Counter((s.date.year, s.date.month) for s in realised)
    return max(per_month.values(), default=0)


def _is_slow(session: SportSession) -> bool:
    return bool(session.distance_km and session.duree_secondes and session.distance_km >= 5
                and session.duree_secondes / session.distance_km > SLOW_PACE_SEC_PER_KM)


def _is_fast_mount(session: SportSession) -> bool:
    return bool(session.distance_km and session.duree_secondes and session.distance_km >= 5
                and session.distance_km / (session.duree_secondes / 3600) >= 13.0)


def _is_palindrome_distance(session: SportSession) -> bool:
    if not session.distance_km:
        return False
    digits = f"{session.distance_km:.2f}".replace(".", "").lstrip("0")
    return len(digits) >= 3 and digits == digits[::-1]


def _is_42(session: SportSession) -> bool:
    return (session.distance_km is not None and round(session.distance_km, 2) == 4.2) or session.duree_secondes == 2520


# ---------- Constructeurs de badges ----------

def _counted(badge_id: str, title: str, description: str, icon: str, rarity: str,
             current: float, target: float, unit: str) -> SportBadge:
    return SportBadge(
        id=badge_id, title=title, description=description, icon=icon, category=BadgeCategory.POP_CULTURE,
        is_unlocked=current >= target, current_value=float(current), target_value=float(target), unit=unit,
        progress_pct=min(100, int(current / target * 100)), rarity=rarity,
    )


def _condition(badge_id: str, title: str, description: str, icon: str, rarity: str, unlocked: bool) -> SportBadge:
    return SportBadge(id=badge_id, title=title, description=description, icon=icon,
                      category=BadgeCategory.POP_CULTURE, is_unlocked=unlocked, rarity=rarity)


def _secret(badge_id: str, revealed_title: str, revealed_desc: str, icon: str, hint_emoji: str, hint: str,
            rarity: str, unlocked: bool) -> SportBadge:
    """Secret : nom et émoji cachés (🔒 + énigme) jusqu'au déblocage."""
    return SportBadge(
        id=badge_id,
        title=revealed_title if unlocked else f"Badge Secret {hint_emoji}",
        description=revealed_desc if unlocked else hint,
        icon=icon if unlocked else "🔒",
        category=BadgeCategory.SECRET, is_unlocked=unlocked, is_secret=True,
        current_value=1.0 if unlocked else 0.0, target_value=1.0, progress_pct=100 if unlocked else 0, rarity=rarity,
    )


# ---------- Catalogue ----------

def _asterix(realised: List[SportSession]) -> List[SportBadge]:
    fractionnes = _count_type(realised, SportSessionType.FRACTIONNE)
    return [
        _counted("pop_asterix_a38", "Le Laissez-passer A-38 📋", "38 fractionnés : le formulaire enfin tamponné !",
                 "📋", "argent", fractionnes, 38, "fractionnés"),
        _counted("pop_asterix_marmite", "Tombé dans la Marmite 🧪", "7 séances en 7 jours : la potion fait effet !",
                 "🧪", "argent", _max_in_window(realised, 7), 7, "séances"),
        _counted("pop_asterix_12_travaux", "Les 12 Travaux 🏛️", "12 semaines d'affilée à au moins 3 séances",
                 "🏛️", "or", _best_week_streak(realised, 3), 12, "semaines"),
        _counted("pop_asterix_rome", "Rome ne s'est pas faite en un jour 🏟️",
                 "52 semaines d'affilée avec au moins une séance", "🏟️", "diamant",
                 _best_week_streak(realised, 1), 52, "semaines"),
        _condition("pop_asterix_banquet", "Banquet au Village 🐗", "Finir la sortie autour d'un festin de sangliers",
                   "🐗", "bronze", _any_keyword(realised, ["sanglier", "banquet", "festin"])),
        _condition("pop_asterix_idefix", "Idéfix Approuve 🐕", "Un chien a partagé ta séance (ou t'a coursé)",
                   "🐕", "bronze", _any_keyword(realised, ["chien"])),
        _condition("pop_asterix_ciel", "Le Ciel nous Tombe sur la Tête 🌩️", "Courir sous une météo apocalyptique (9/10)",
                   "🌩️", "argent",
                   any((s.meteo_note or 0) >= 9 for s in realised) or _any_keyword(realised, ["grêle", "grele"])),
    ]


def _warcraft(realised: List[SportSession]) -> List[SportBadge]:
    ef = _count_type(realised, SportSessionType.EF)
    wednesdays = sum(1 for s in realised if s.date.weekday() == 2)
    return [
        _condition("pop_wow_leeroy", "Leeroy Jenkins ! 🐔", "Foncer sans réfléchir : RPE 10 ou parti bien trop vite",
                   "🐔", "bronze",
                   any(s.ressenti_rpe == 10 for s in realised)
                   or _any_keyword(realised, ["parti trop vite", "partie trop vite", "explos"])),
        _counted("pop_wow_whelps", "Many Whelps! 🐉", "50 fractionnés : gérez les dragonnets !",
                 "🐉", "or", _count_type(realised, SportSessionType.FRACTIONNE), 50, "fractionnés"),
        _condition("pop_wow_monture", "Monture Épique 🐎", "Au moins 13 km/h de moyenne sur 5 km ou plus",
                   "🐎", "or", any(_is_fast_mount(s) for s in realised)),
        _counted("pop_wow_reset", "Reset du Mercredi 📅", "52 séances un mercredi, jour du reset des raids EU",
                 "📅", "argent", wednesdays, 52, "mercredis"),
        _counted("pop_wow_honore", "Réputation : Honoré 🤝", "50 sorties d'endurance fondamentale",
                 "🤝", "bronze", ef, 50, "EF"),
        _counted("pop_wow_revere", "Réputation : Révéré 🎖️", "100 sorties d'endurance fondamentale",
                 "🎖️", "argent", ef, 100, "EF"),
        _counted("pop_wow_exalte", "Réputation : Exalté 💠", "200 sorties d'endurance fondamentale",
                 "💠", "or", ef, 200, "EF"),
    ]


def _middle_earth(realised: List[SportSession]) -> List[SportBadge]:
    return [
        _condition("pop_lotr_retour_roi", "Le Retour du Roi 👑", "Revenir après au moins 3 semaines d'exil",
                   "👑", "argent", _longest_break_days(realised) >= 21),
        _counted("pop_lotr_grand_pas", "Grand-Pas 🏹", "3 sorties de 15 km ou plus, comme un Rôdeur du Nord",
                 "🏹", "or", sum(1 for s in realised if (s.distance_km or 0) >= 15), 3, "sorties"),
        _counted("pop_lotr_trois_chasseurs", "Les Trois Chasseurs 🧝",
                 "45 lieues (217 km) en 3 mois glissants, sur la piste des Uruk-hai",
                 "🧝", "or", round(_max_in_window(realised, ROLLING_WINDOW_DAYS, lambda s: s.distance_km or 0.0), 2),
                 LOTR_45_LEAGUES_KM, "km"),
        _condition("pop_lotr_poney", "Au Poney Fringant 🍺", "Une bière bien méritée après la séance",
                   "🍺", "bronze", _any_keyword(realised, ["bière", "biere", "pinte"])),
    ]


def _cosmere(realised: List[SportSession]) -> List[SportBadge]:
    total = len(realised)
    breaths = [(50, "bronze"), (200, "argent"), (600, "or"), (1000, "diamant"), (2000, "mythique")]
    return [
        _counted("pop_roshar_chull", "Chull Express 🐢", "20 séances à plus de 7:30 /km sur 5 km ou plus : lent mais sûr",
                 "🐢", "bronze", sum(1 for s in realised if _is_slow(s)), 20, "séances"),
        _counted("pop_roshar_gloryspren", "Sprens de Gloire ✨", "Battre 15 fois son record de plus longue sortie",
                 "✨", "or", _longest_run_records_beaten(realised), 15, "records"),
        _condition("pop_roshar_hoid", "Une Blague pour Hoid 🎭", "Une séance qui t'a fait rire (Hoid approuve)",
                   "🎭", "bronze", _any_keyword(realised, ["blague", "rigol"])),
        _counted("pop_scadrial_fils_des_brumes", "Fils-des-Brumes 🌫️", "25 séances dans le même mois : tu brûles tous tes métaux !",
                 "🌫️", "or", _max_sessions_in_a_month(realised), 25, "séances"),
        *[
            _counted(f"pop_nalthis_souffles_{n}", f"{n:,} Souffles 🌈".replace(",", " "),
                     f"{n:,} séances : les couleurs se ravivent autour de toi".replace(",", " "),
                     "🌈", rarity, total, n, "séances")
            for n, rarity in breaths
        ],
    ]


def _secrets(realised: List[SportSession]) -> List[SportBadge]:
    def on(month: int, day: int) -> bool:
        return any(s.date.month == month and s.date.day == day for s in realised)

    return [
        _secret("secret_sang_de_nuit", "Sang-de-Nuit 🗡️", "« Veux-tu détruire le mal ? » Oui, en courant.",
                "🗡️", "🗡️", "Une épée qui parle a une question pour toi...", "or",
                _any_keyword(realised, ["épée", "epee", "détruire le mal", "detruire le mal"])),
        _secret("secret_nouvel_an", "Bonne Résolution 🎆", "Courir un 1er janvier", "🎆", "🎆",
                "Un jour où tout le monde dort encore...", "argent", on(1, 1)),
        _secret("secret_noel", "Lutin Coureur 🎄", "Courir le jour de Noël", "🎄", "🎄",
                "Avant ou après la dinde ?", "argent", on(12, 25)),
        _secret("secret_vendredi_13", "Chat Noir 🐈‍⬛", "Courir un vendredi 13", "🐈‍⬛", "🐈‍⬛",
                "Les superstitieux restent au lit ce jour-là...", "bronze",
                any(s.date.day == 13 and s.date.weekday() == 4 for s in realised)),
        _secret("secret_42", "La Grande Question 🌌", "4,2 km ou 42:00 pile : la réponse à tout", "🌌", "🌌",
                "Une réponse à la vie, l'univers et le reste...", "or", any(_is_42(s) for s in realised)),
        _secret("secret_palindrome", "Palindrome 🔁", "Une distance qui se lit dans les deux sens (ex. 12,21 km)",
                "🔁", "🔁", "À l'endroit comme à l'envers...", "argent", any(_is_palindrome_distance(s) for s in realised)),
        _secret("secret_29_fevrier", "Jour Bonus 🐸", "Courir un 29 février", "🐸", "🐸",
                "Un jour qui n'existe qu'une année sur quatre...", "or", on(2, 29)),
    ]


def evaluate_fun_badges(sessions: List[SportSession]) -> List[SportBadge]:
    """Évalue les trophées ajoutés le 16/11 sur les séances réalisées."""
    realised = [s for s in sessions if s.statut == SportSessionStatus.REALISE]
    return [*_asterix(realised), *_warcraft(realised), *_middle_earth(realised), *_cosmere(realised), *_secrets(realised)]

