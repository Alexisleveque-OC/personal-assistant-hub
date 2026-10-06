"""Tests unitaires pour le moteur de gamification, badges de dopamine et anecdotes sportives."""
from datetime import date
from typing import List

import pytest

from app.connectors.sheets.sport_models import (
    BadgeCategory,
    SportBadge,
    SportFunFact,
    SportGamificationSummary,
    SportSession,
    SportSessionStatus,
    SportSessionType,
)
from app.core.sport_gamification_service import SportGamificationService


def _create_mock_session(
    date_str: str,
    statut: str = "Réalisé",
    type_seance: str = "EF",
    distance_km: float = 10.0,
    duree_sec: int = 3600,
    d_plus: int = 100,
    rpe: int = 5,
    remarques: str = "",
) -> SportSession:
    d = date.fromisoformat(date_str)
    return SportSession(
        date=d,
        semaine=d.isocalendar()[1],
        statut=SportSessionStatus(statut),
        type_seance=SportSessionType(type_seance),
        distance_km=distance_km,
        duree_secondes=duree_sec,
        denivele_d_plus=d_plus,
        ressenti_rpe=rpe,
        remarques=remarques,
    )


def test_gamification_summary_empty_history():
    """Vérifie que le service fonctionne de manière sûre avec un historique vide."""
    service = SportGamificationService()
    summary = service.compute_summary([])

    assert isinstance(summary, SportGamificationSummary)
    assert summary.total_badges > 0
    assert summary.unlocked_count == 0
    assert len(summary.personal_records) >= 3
    assert len(summary.fun_facts) > 0


def test_distance_milestones_and_regular_dopamine():
    """Vérifie le déblocage régulier des paliers de distance (10k, 42.2k, 100k, 200k)."""
    service = SportGamificationService()
    sessions = [
        _create_mock_session("2026-10-01", distance_km=15.0),
        _create_mock_session("2026-10-02", distance_km=30.0), # Total 45 km -> 10k et 42.2k débloqués
        _create_mock_session("2026-10-03", distance_km=60.0), # Total 105 km -> 100k débloqué
    ]
    summary = service.compute_summary(sessions)

    badges_by_id = {b.id: b for b in summary.badges}

    assert badges_by_id["dist_10k"].is_unlocked is True
    assert badges_by_id["dist_marathon"].is_unlocked is True
    assert badges_by_id["dist_100k"].is_unlocked is True
    assert badges_by_id["dist_200k"].is_unlocked is False
    assert badges_by_id["dist_200k"].current_value == 105.0
    assert badges_by_id["dist_200k"].progress_pct == 52


def test_imminent_milestone_detection():
    """Vérifie la détection d'un palier imminent pour motiver l'utilisateur (Chronique & Coach)."""
    service = SportGamificationService()
    # 96 km cumulés -> à 4 km du palier 100k
    sessions = [
        _create_mock_session("2026-10-01", distance_km=50.0),
        _create_mock_session("2026-10-02", distance_km=46.0),
    ]
    summary = service.compute_summary(sessions)

    assert len(summary.imminent_milestones) > 0
    imminent = summary.imminent_milestones[0]
    assert imminent.badge_id == "dist_100k"
    assert round(imminent.remaining, 1) == 4.0
    assert "100" in imminent.message


def test_elevation_milestones():
    """Vérifie le déblocage des paliers de dénivelé positif cumulé (Tour Eiffel, 1000m, etc.)."""
    service = SportGamificationService()
    sessions = [
        _create_mock_session("2026-10-01", d_plus=200),
        _create_mock_session("2026-10-02", d_plus=150), # Total 350m -> Tour Eiffel (300m) débloqué
        _create_mock_session("2026-10-03", d_plus=700), # Total 1050m -> Kilomètre Vertical (1000m) débloqué
    ]
    summary = service.compute_summary(sessions)
    badges = {b.id: b for b in summary.badges}

    assert badges["dplus_300m"].is_unlocked is True
    assert badges["dplus_1000m"].is_unlocked is True
    assert badges["dplus_2500m"].is_unlocked is False


def test_secret_easter_egg_badges():
    """Vérifie le déblocage des badges cachés/secrets (Le Déneigéré, Pi-Runner, etc.)."""
    service = SportGamificationService()
    sessions = [
        _create_mock_session("2026-10-01", remarques="Il faisait un froid de canard et il neigeait dru"),
        _create_mock_session("2026-10-02", distance_km=3.14, duree_sec=1100),
        _create_mock_session("2026-10-03", duree_sec=2400), # 40 min pile -> 2400s (seconde pile)
    ]
    summary = service.compute_summary(sessions)
    badges = {b.id: b for b in summary.badges}

    # Le Déneigéré (badge secret)
    assert badges["secret_deneigere"].is_unlocked is True
    assert badges["secret_deneigere"].is_secret is True
    assert "Déneigéré" in badges["secret_deneigere"].title

    # Pi Runner
    assert badges["secret_pi_runner"].is_unlocked is True

    # Chrono d'orfèvre (pile à la minute/seconde)
    assert badges["secret_chrono_rond"].is_unlocked is True


def test_absurd_cosmic_badges_and_fun_facts():
    """Vérifie le badge absurde Road to the Moon et les équivalences géographiques/énergétiques."""
    service = SportGamificationService()
    sessions = [
        _create_mock_session("2026-10-01", distance_km=50.0, d_plus=650),
    ]
    summary = service.compute_summary(sessions)
    badges = {b.id: b for b in summary.badges}

    # Road to the Moon (384 400 km)
    assert "absurd_moon" in badges
    moon_badge = badges["absurd_moon"]
    assert moon_badge.target_value == 384400.0
    assert moon_badge.current_value == 50.0
    assert moon_badge.is_unlocked is False

    # Fun facts
    facts = summary.fun_facts
    geo_facts = [f for f in facts if f.category == "geo"]
    vert_facts = [f for f in facts if f.category == "vertical"]
    assert len(geo_facts) > 0
    assert len(vert_facts) > 0
    # D+ 650m -> au moins 2 fois la Tour Eiffel
    assert any("Tour Eiffel" in f.text for f in vert_facts)


def test_personal_records_detection():
    """Vérifie l'identification correcte des records personnels (distance max, D+ max, allure)."""
    service = SportGamificationService()
    sessions = [
        _create_mock_session("2026-10-01", distance_km=8.0, duree_sec=2400, d_plus=50), # 5:00 min/km
        _create_mock_session("2026-10-02", distance_km=14.5, duree_sec=5200, d_plus=320), # Plus longue et plus de D+
        _create_mock_session("2026-10-03", distance_km=5.0, duree_sec=1350, d_plus=20), # 4:30 min/km -> Meilleure allure
    ]
    summary = service.compute_summary(sessions)
    prs = {pr.record_type: pr for pr in summary.personal_records}

    assert prs["longest_run"].value == 14.5
    assert prs["max_elevation"].value == 320
    assert "4:30" in prs["best_pace"].formatted_value


def test_morning_chronicle_snippet_prefers_imminent_milestone():
    """Vérifie que la chronique matinale met en avant un palier imminent s'il existe."""
    service = SportGamificationService()
    # 97 km -> plus que 3 km pour 100 km
    sessions = [_create_mock_session("2026-10-01", distance_km=97.0)]
    summary = service.compute_summary(sessions)
    snippet = service.get_morning_chronicle_snippet(summary)

    assert "🎯" in snippet
    assert "100" in snippet
    assert "3.0 km" in snippet


def test_major_announcements_omg_marathons_and_big_numbers():
    """Vérifie le déclenchement d'annonces marquantes (ex: 'OMG t'as couru 10 marathons !')."""
    service = SportGamificationService()
    # 430 km -> plus de 10 marathons (10 * 42.195 = 421.95 km)
    sessions = [
        _create_mock_session("2026-10-01", distance_km=215.0, d_plus=5500),
        _create_mock_session("2026-10-02", distance_km=215.0, d_plus=5000), # Total 430 km, 10500 m D+
    ]
    summary = service.compute_summary(sessions)

    assert hasattr(summary, "announcements")
    announcements_text = " ".join(summary.announcements)
    assert "OMG" in announcements_text
    assert "10 marathons" in announcements_text
    # Annonce D+ 10 000 m
    assert "10 000 m" in announcements_text or "10000" in announcements_text


def test_systematic_milestones_every_100km_and_1000m_elevation():
    """Vérifie la présence des badges tous les 100 km, 1000 km, et dénivelé 1000m et 10000m."""
    service = SportGamificationService()
    # 250 km, 2200 m D+
    sessions = [
        _create_mock_session("2026-10-01", distance_km=150.0, d_plus=1200),
        _create_mock_session("2026-10-02", distance_km=100.0, d_plus=1000),
    ]
    summary = service.compute_summary(sessions)
    badge_ids = {b.id: b for b in summary.badges}

    # 100 km et 200 km débloqués, 300 km en cours
    assert badge_ids["dist_100k"].is_unlocked is True
    assert badge_ids["dist_200k"].is_unlocked is True
    assert badge_ids["dist_300k"].is_unlocked is False
    assert badge_ids["dist_300k"].current_value == 250.0

    # D+ 1000m et 2000m débloqués, 3000m en cours
    assert badge_ids["dplus_1000m"].is_unlocked is True
    assert badge_ids["dplus_2000m"].is_unlocked is True
    assert badge_ids["dplus_3000m"].is_unlocked is False

    # Gros chiffres visibles en ligne de mire
    assert "dist_1000k" in badge_ids
    assert "dplus_10000m" in badge_ids


def test_daily_spotlight_with_planned_session_crossing_milestone():
    """Vérifie l'annonce du jour personnalisée lorsqu'une séance prévue va faire passer un cap."""
    service = SportGamificationService()
    # 95 km réalisés, et une séance PRÉVUE de 10 km aujourd'hui (date de référence : 2026-10-06)
    ref_date = date(2026, 10, 6)
    sessions = [
        _create_mock_session("2026-10-01", distance_km=95.0),
        _create_mock_session("2026-10-06", statut="Prévu", distance_km=10.0),
    ]
    summary = service.compute_summary(sessions, reference_date=ref_date)

    assert summary.daily_spotlight is not None
    assert "100 km" in summary.daily_spotlight or "100" in summary.daily_spotlight
    assert "aujourd'hui" in summary.daily_spotlight.lower() or "séance" in summary.daily_spotlight.lower()


def test_mono_session_feats_distance_and_duration():
    """Vérifie le déblocage des exploits réalisés en une seule séance (10k, 21k, 42k, 1h, 2h, etc.)."""
    service = SportGamificationService()
    sessions = [
        _create_mock_session("2026-10-01", distance_km=10.5, duree_sec=3600), # 10k d'un coup + 1h
        _create_mock_session("2026-10-02", distance_km=21.2, duree_sec=7200), # Semi d'un coup + 2h
    ]
    summary = service.compute_summary(sessions)
    badge_ids = {b.id: b for b in summary.badges}

    # Mono-séance distance
    assert badge_ids["mono_dist_10k"].is_unlocked is True
    assert badge_ids["mono_dist_semi"].is_unlocked is True
    assert badge_ids["mono_dist_marathon"].is_unlocked is False
    assert badge_ids["mono_dist_100k"].is_unlocked is False # L'ultra absurde

    # Mono-séance durée
    assert badge_ids["mono_duree_1h"].is_unlocked is True
    assert badge_ids["mono_duree_2h"].is_unlocked is True
    assert badge_ids["mono_duree_3h"].is_unlocked is False
    assert badge_ids["mono_duree_24h"].is_unlocked is False # Absurde 24h d'affilée


def test_strength_and_weather_progressive_badges():
    """Vérifie la progression jusqu'à 100 séances de renfo et les paliers météo difficile."""
    service = SportGamificationService()
    # 6 séances de renforcement, 2 séances météo pluie
    sessions = [
        _create_mock_session(f"2026-09-{i:02d}", type_seance="Renforcement", distance_km=0.0, duree_sec=1800)
        for i in range(1, 7)
    ]
    sessions.append(_create_mock_session("2026-09-10", remarques="Pluie battante et vent violent"))
    sessions.append(_create_mock_session("2026-09-11", remarques="Averse continue"))

    summary = service.compute_summary(sessions)
    badge_ids = {b.id: b for b in summary.badges}

    # Renfo progressif
    assert badge_ids["renfo_5"].is_unlocked is True
    assert badge_ids["renfo_10"].is_unlocked is False
    assert "renfo_25" in badge_ids
    assert "renfo_50" in badge_ids
    assert "renfo_100" in badge_ids

    # Météo difficile progressive
    assert badge_ids["meteo_1"].is_unlocked is True
    assert badge_ids["meteo_5"].is_unlocked is False
    assert "meteo_10" in badge_ids
    assert "meteo_20" in badge_ids


def test_legendary_duration_tiers_in_hours_and_days():
    """Vérifie les paliers de volume horaire comparés en jours (96h, 240h, 480h, etc.)."""
    service = SportGamificationService()
    # 100 heures d'effort (360 000 sec) -> 96h débloqué (4 jours complets)
    sessions = [
        _create_mock_session("2026-10-01", duree_sec=180000),
        _create_mock_session("2026-10-02", duree_sec=180000),
    ]
    summary = service.compute_summary(sessions)
    badge_ids = {b.id: b for b in summary.badges}

    assert badge_ids["time_96h"].is_unlocked is True
    assert "4 jours" in badge_ids["time_96h"].description
    assert badge_ids["time_240h"].is_unlocked is False
    assert "10 jours" in badge_ids["time_240h"].description
    assert "time_480h" in badge_ids
    assert "time_960h" in badge_ids
    assert "time_1920h" in badge_ids


def test_pop_culture_easter_eggs_asterix_lotr_and_roshar():
    """Vérifie au moins 15 badges de pop culture (Astérix Otis, Seigneur des Anneaux, Roshar)."""
    service = SportGamificationService()
    sessions = [
        # Astérix / Otis
        _create_mock_session("2026-10-01", remarques="Je ne crois pas qu'il y ait de bonne ou de mauvaise situation"),
        _create_mock_session("2026-10-02", remarques="Pas de pierres, pas de construction ! Les dalles sont posées."),
        _create_mock_session("2026-10-03", remarques="Quelle chaleur, un vrai lion mort sous le soleil du désert"),
        # Seigneur des Anneaux
        _create_mock_session("2026-10-04", remarques="Grosse faim de retour à la maison, prêt pour le deuxième petit-déjeuner"),
        _create_mock_session("2026-10-05", d_plus=250, remarques="Vous ne passerez pas face à cette côte impitoyable"),
        _create_mock_session("2026-10-06", remarques="Un tour complet, une boucle parfaite autour du lac"),
        # Brandon Sanderson - Archives de Roshar
        _create_mock_session("2026-10-07", rpe=10, remarques="Séance Pont Quatre, la vie avant la mort, mental à 100%"),
        _create_mock_session("2026-10-08", remarques="Au cœur de la haute-tempête sous un déluge torrentiel"),
        _create_mock_session("2026-10-09", distance_km=5.0, duree_sec=1200, remarques="Marcheur du vent porté par les rafales"),
        _create_mock_session("2026-10-10", d_plus=180, remarques="Sentier caillouteux comme un danseur de pierre"),
    ]
    summary = service.compute_summary(sessions)
    badge_ids = {b.id: b for b in summary.badges}

    # Vérification d'au moins 15 badges pop culture définis dans le catalogue
    pop_badges = [b for b in summary.badges if b.category == BadgeCategory.POP_CULTURE]
    assert len(pop_badges) >= 15

    # Déblocages vérifiés
    assert badge_ids["pop_otis_situation"].is_unlocked is True
    assert badge_ids["pop_otis_pierres"].is_unlocked is True
    assert badge_ids["pop_otis_lion"].is_unlocked is True

    assert badge_ids["pop_lotr_second_dejeuner"].is_unlocked is True
    assert badge_ids["pop_lotr_vous_ne_passerez_pas"].is_unlocked is True
    assert badge_ids["pop_lotr_anneau_unique"].is_unlocked is True
    assert "pop_lotr_mordor" in badge_ids # Trajet de Frodon (2 850 km)

    assert badge_ids["pop_roshar_pont_quatre"].is_unlocked is True
    assert badge_ids["pop_roshar_haute_tempete"].is_unlocked is True
    assert badge_ids["pop_roshar_marcheur_du_vent"].is_unlocked is True
    assert badge_ids["pop_roshar_danseur_de_pierre"].is_unlocked is True


def test_weekly_consistency_badges_7_days_and_8_weeks():
    """Vérifie les badges 7 séances dans la même semaine et 4 séances par semaine pendant 8 semaines d'affilée."""
    service = SportGamificationService()
    sessions = []
    # 8 semaines consécutives : semaines 33 à 40 de l'année 2026
    # Semaines 33 à 39 : 4 séances par semaine (lundi, mardi, jeudi, samedi)
    for wk in range(33, 40):
        monday = date.fromisocalendar(2026, wk, 1)
        tuesday = date.fromisocalendar(2026, wk, 2)
        thursday = date.fromisocalendar(2026, wk, 4)
        saturday = date.fromisocalendar(2026, wk, 6)
        for d in [monday, tuesday, thursday, saturday]:
            sessions.append(_create_mock_session(d.isoformat()))

    # Semaine 40 : 7 séances complètes (du lundi au dimanche)
    for day_of_week in range(1, 8):
        d = date.fromisocalendar(2026, 40, day_of_week)
        sessions.append(_create_mock_session(d.isoformat()))

    summary = service.compute_summary(sessions)
    badge_ids = {b.id: b for b in summary.badges}

    # 7 séances dans la même semaine
    assert badge_ids["reg_7_seances_semaine"].is_unlocked is True
    assert badge_ids["reg_7_seances_semaine"].current_value == 7.0

    # 4 séances par semaine pendant 8 semaines d'affilée (semaines 33 à 40)
    assert badge_ids["reg_4seances_8semaines"].is_unlocked is True
    assert badge_ids["reg_4seances_8semaines"].current_value == 8.0


