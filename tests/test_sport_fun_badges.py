"""Nouveaux trophées pop-culture et secrets (ROADMAP Étape 3, seuils calibrés sur les données réelles le 16/11)."""
from datetime import date, timedelta
from typing import List, Optional

import pytest

from app.connectors.sheets.sport_models import BadgeCategory, SportBadge, SportSession, SportSessionStatus, SportSessionType
from app.core.sport_fun_badges import evaluate_fun_badges
from app.core.sport_gamification_service import SportGamificationService


def _s(day: str, type_seance: str = "EF", km: Optional[float] = 8.0, sec: Optional[int] = 2880, rpe: int = 5,
       meteo: Optional[int] = None, remarques: str = "", statut: str = "Réalisé") -> SportSession:
    d = date.fromisoformat(day)
    return SportSession(date=d, semaine=d.isocalendar()[1], statut=SportSessionStatus(statut),
                        type_seance=SportSessionType(type_seance), distance_km=km, duree_secondes=sec,
                        ressenti_rpe=rpe, meteo_note=meteo, remarques=remarques)


def _days(start: str, count: int, step: int = 1, **kw) -> List[SportSession]:
    first = date.fromisoformat(start)
    return [_s((first + timedelta(days=i * step)).isoformat(), **kw) for i in range(count)]


def _get(sessions: List[SportSession], badge_id: str) -> SportBadge:
    return next(b for b in evaluate_fun_badges(sessions) if b.id == badge_id)


def test_catalog_ids_are_unique_and_categorised():
    badges = evaluate_fun_badges([])
    ids = [b.id for b in badges]
    assert len(ids) == len(set(ids)) == 34
    assert {b.category for b in badges} == {BadgeCategory.POP_CULTURE, BadgeCategory.SECRET}
    assert all(not b.is_unlocked and b.unlocked_at is None for b in badges)
    assert {b.rarity for b in badges} <= {"bronze", "argent", "or", "diamant", "mythique"}


# ---------- Trophées à compteur : progression affichée ----------

@pytest.mark.parametrize("badge_id, sessions, unlocked, current, target, unit", [
    ("pop_asterix_a38", _days("2026-01-01", 38, type_seance="Fractionné"), True, 38, 38, "fractionnés"),
    ("pop_asterix_a38", _days("2026-01-01", 34, type_seance="Fractionné"), False, 34, 38, "fractionnés"),
    ("pop_wow_whelps", _days("2026-01-01", 50, type_seance="Fractionné"), True, 50, 50, "fractionnés"),
    ("pop_asterix_marmite", _days("2026-03-02", 7), True, 7, 7, "séances"),
    ("pop_asterix_marmite", _days("2026-03-02", 6) + _days("2026-03-09", 1), False, 6, 7, "séances"),
    ("pop_asterix_12_travaux", _days("2026-01-05", 42, step=2), True, 12, 12, "semaines"),
    ("pop_asterix_12_travaux", _days("2026-01-05", 27, step=2), False, 7, 12, "semaines"),
    ("pop_asterix_rome", _days("2025-01-06", 52, step=7), True, 52, 52, "semaines"),
    ("pop_asterix_rome", _days("2025-01-06", 51, step=7), False, 51, 52, "semaines"),
    ("pop_wow_reset", _days("2025-01-01", 52, step=7), True, 52, 52, "mercredis"),
    ("pop_wow_honore", _days("2025-01-01", 50, type_seance="EF"), True, 50, 50, "EF"),
    ("pop_wow_revere", _days("2025-01-01", 60, type_seance="EF"), False, 60, 100, "EF"),
    ("pop_wow_exalte", _days("2025-01-01", 200, type_seance="EF"), True, 200, 200, "EF"),
    ("pop_lotr_grand_pas", _days("2026-01-01", 3, step=10, km=15.0, sec=5400), True, 3, 3, "sorties"),
    ("pop_lotr_trois_chasseurs", _days("2026-01-01", 22, step=4, km=10.0), True, 220, 217, "km"),
    ("pop_lotr_trois_chasseurs", _days("2026-01-01", 22, step=5, km=10.0), False, 190, 217, "km"),
    ("pop_roshar_chull", _days("2026-01-01", 20, km=5.0, sec=2400), True, 20, 20, "séances"),
    ("pop_roshar_gloryspren", [_s(f"2026-01-{i + 1:02d}", km=5.0 + i) for i in range(16)], True, 15, 15, "records"),
    ("pop_scadrial_fils_des_brumes", _days("2026-03-01", 25), True, 25, 25, "séances"),
    ("pop_scadrial_fils_des_brumes", _days("2026-03-20", 25), False, 13, 25, "séances"),
    ("pop_nalthis_souffles_50", _days("2025-01-01", 50), True, 50, 50, "séances"),
    ("pop_nalthis_souffles_600", _days("2025-01-01", 218), False, 218, 600, "séances"),
])
def test_counted_trophies_show_their_progress(badge_id, sessions, unlocked, current, target, unit):
    badge = _get(sessions, badge_id)
    assert (badge.is_unlocked, badge.current_value, badge.target_value, badge.unit) == (unlocked, current, target, unit)
    assert badge.progress_pct == min(100, int(current / target * 100))


def test_trois_chasseurs_counts_three_rolling_months_not_the_whole_history():
    sessions = _days("2025-01-01", 10, km=20.0) + _days("2025-09-01", 10, km=20.0)
    assert _get(sessions, "pop_lotr_trois_chasseurs").current_value == 200


def test_not_realised_sessions_are_ignored():
    assert _get(_days("2026-01-01", 38, type_seance="Fractionné", statut="Prévu"), "pop_asterix_a38").current_value == 0


# ---------- Trophées à condition ----------

@pytest.mark.parametrize("badge_id, session", [
    ("pop_asterix_banquet", _s("2026-01-01", remarques="Gros festin après la sortie")),
    ("pop_asterix_idefix", _s("2026-01-01", remarques="Un chien m'a suivi")),
    ("pop_asterix_ciel", _s("2026-01-01", meteo=9)),
    ("pop_asterix_ciel", _s("2026-01-01", remarques="Averse de grêle")),
    ("pop_wow_leeroy", _s("2026-01-01", rpe=10)),
    ("pop_wow_leeroy", _s("2026-01-01", remarques="Parti trop vite, explosé au 5e")),
    ("pop_wow_monture", _s("2026-01-01", km=5.0, sec=1380)),
    ("pop_lotr_poney", _s("2026-01-01", remarques="Une pinte bien méritée")),
    ("pop_roshar_hoid", _s("2026-01-01", remarques="On a bien rigolé")),
    ("secret_sang_de_nuit", _s("2026-01-01", remarques="Je vais détruire le mal")),
    ("secret_nouvel_an", _s("2026-01-01")),
    ("secret_noel", _s("2024-12-25")),
    ("secret_vendredi_13", _s("2026-03-13")),
    ("secret_42", _s("2026-01-02", km=4.2)),
    ("secret_42", _s("2026-01-02", sec=2520)),
    ("secret_palindrome", _s("2026-01-02", km=12.21)),
    ("secret_29_fevrier", _s("2028-02-29")),
])
def test_condition_trophies_unlock(badge_id, session):
    assert _get([session], badge_id).is_unlocked is True


@pytest.mark.parametrize("badge_id, session", [
    ("pop_wow_monture", _s("2026-01-01", km=4.0, sec=900)),  # trop court
    ("pop_asterix_ciel", _s("2026-01-01", meteo=8)),
    ("secret_vendredi_13", _s("2026-02-12")),  # jeudi 12
    ("secret_vendredi_13", _s("2026-01-13")),  # mardi 13
    ("secret_palindrome", _s("2026-01-02", km=12.12)),
    ("secret_42", _s("2026-01-02", km=4.25)),
])
def test_condition_trophies_stay_locked(badge_id, session):
    assert _get([session], badge_id).is_unlocked is False


def test_return_of_the_king_needs_a_three_week_break_then_a_comeback():
    assert _get([_s("2026-01-01"), _s("2026-01-22")], "pop_lotr_retour_roi").is_unlocked is True
    assert _get([_s("2026-01-01"), _s("2026-01-21")], "pop_lotr_retour_roi").is_unlocked is False


def test_locked_secrets_hide_their_name_and_emoji():
    badge = _get([], "secret_noel")
    assert badge.is_secret and badge.icon == "🔒" and badge.title.startswith("Badge Secret")
    unlocked = _get([_s("2024-12-25")], "secret_noel")
    assert unlocked.icon != "🔒" and not unlocked.title.startswith("Badge Secret")


# ---------- Intégration au service ----------

def test_service_includes_the_new_trophies_with_unlock_dates():
    summary = SportGamificationService().compute_summary([_s("2024-12-20"), _s("2024-12-25")])
    noel = next(b for b in summary.badges if b.id == "secret_noel")
    assert noel.is_unlocked and noel.unlocked_at == "2024-12-25"
    assert summary.total_badges == len(summary.badges)


@pytest.mark.parametrize("remarques, unlocked", [
    ("C'était dur aujourd'hui", True),
    ("Durée un peu longue, mais ça allait", False),
    ("Durant la sortie, rien à signaler", False),
])
def test_pain_spren_matches_the_whole_word_dur(remarques, unlocked):
    summary = SportGamificationService().compute_summary([_s("2026-01-01", remarques=remarques)])
    assert next(b for b in summary.badges if b.id == "pop_roshar_spren_douleur").is_unlocked is unlocked
