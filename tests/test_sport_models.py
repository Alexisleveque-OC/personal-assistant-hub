"""Tests unitaires pour les modèles Pydantic et calculs du module Sport (Running)."""
from datetime import date
import pytest
from pydantic import ValidationError

from app.connectors.sheets.sport_models import (
    SportSession,
    SportSessionCreate,
    SportSessionStatus,
    SportSessionType,
    SportWeeklySummary,
    calculate_km_effort,
    calculate_speed_kmh,
    calculate_pace_min_km,
    calculate_rpe_load,
    format_pace,
)


def test_calculate_km_effort_standard():
    """Vérifie la formule standard : km + D+/100."""
    # 8 km avec 150m de D+ = 8 + 1.5 = 9.5 km-effort
    assert calculate_km_effort(8.0, 150) == 9.5
    # Plat : 10 km avec 0 D+ = 10.0
    assert calculate_km_effort(10.0, 0) == 10.0
    # D+ négatif ou None
    assert calculate_km_effort(5.0, None) == 5.0


def test_calculate_speed_and_pace():
    """Vérifie le calcul de la vitesse (km/h) et de l'allure (min/km)."""
    # 10 km en 50 minutes (3000 secondes) -> 12 km/h, 5:00 min/km
    duration_seconds = 50 * 60
    speed = calculate_speed_kmh(10.0, duration_seconds)
    pace_seconds = calculate_pace_min_km(10.0, duration_seconds)
    formatted_pace = format_pace(pace_seconds)

    assert pytest.approx(speed, 0.01) == 12.0
    assert pace_seconds == 300  # 5 min = 300 s
    assert formatted_pace == "05:00"


def test_calculate_rpe_load():
    """Vérifie le calcul de la charge RPE (durée en minutes * RPE)."""
    # 45 minutes avec un ressenti de 6/10 = 270 unités de charge
    assert calculate_rpe_load(45 * 60, 6) == 270
    assert calculate_rpe_load(0, 6) == 0


def test_sport_session_model_creation_and_computed_properties():
    """Vérifie l'instanciation complète d'une séance réalisée avec calcul automatique."""
    session = SportSession(
        date=date(2026, 10, 6),
        semaine=41,
        statut=SportSessionStatus.REALISE,
        type_seance=SportSessionType.EF,
        distance_km=7.5,
        denivele_d_plus=80,
        duree_secondes=43 * 60 + 15,  # 43m15s = 2595s
        ressenti_rpe=6,
        notes="Footing tranquille en forêt",
        strava_id="1234567890",
    )

    assert session.km_effort == 8.3  # 7.5 + 0.8
    assert pytest.approx(session.vitesse_kmh, 0.01) == 10.40
    assert session.allure_formatted == "05:46"
    assert session.charge_rpe == 260  # 43.25 min * 6 = 259.5 -> arrondi 260
    assert session.statut == SportSessionStatus.REALISE


def test_sport_session_model_planned_without_performance():
    """Une séance planifiée peut ne pas avoir encore de durée, vitesse ou allure."""
    session = SportSession(
        date=date(2026, 10, 8),
        semaine=41,
        statut=SportSessionStatus.PLANIFIE,
        type_seance=SportSessionType.FRACTIONNE,
        distance_km=6.0,
        notes="8x(30s/30s)",
    )

    assert session.statut == SportSessionStatus.PLANIFIE
    assert session.vitesse_kmh is None
    assert session.allure_formatted is None
    assert session.km_effort == 6.0


def test_sport_weekly_summary_evolution_and_safety_alerts():
    """Vérifie le diagnostic du mini-coach pour la progression et le plafond des 10%."""
    # Semaine précédente : 20 km-effort
    summary = SportWeeklySummary(
        semaine=41,
        annee=2026,
        nb_seances=3,
        km_total=21.0,
        d_plus_total=100,
        km_effort_total=22.0,
        duree_secondes=7200,
        previous_week_km_effort=20.0,
    )

    # Progression : (22 - 20) / 20 = +10% -> Progression saine
    assert pytest.approx(summary.evolution_charge_pct, 0.01) == 10.0
    assert "Saine" in summary.alerte_securite
    # Plafond conseillé pour S+1 : 22 * 1.10 = 24.2 km-effort
    assert pytest.approx(summary.plafond_conseille_s_plus_1, 0.1) == 24.2


def test_sport_weekly_summary_excessive_progression_alert():
    """Alerte blessure lorsque l'augmentation dépasse +15%."""
    summary = SportWeeklySummary(
        semaine=42,
        annee=2026,
        nb_seances=4,
        km_total=30.0,
        d_plus_total=0,
        km_effort_total=30.0,
        duree_secondes=9000,
        previous_week_km_effort=22.0,  # +36% d'augmentation !
    )

    assert summary.evolution_charge_pct > 15.0
    assert "Risque Blessure" in summary.alerte_securite


def test_sport_session_renforcement_model():
    """Vérifie la modélisation d'une séance de renforcement musculaire sans distance."""
    session = SportSession(
        date=date(2026, 10, 7),
        semaine=41,
        statut=SportSessionStatus.REALISE,
        type_seance=SportSessionType.RENFORCEMENT,
        distance_km=None,
        denivele_d_plus=0,
        duree_secondes=35 * 60,  # 35 min
        ressenti_rpe=7,
        notes="Gainage, fentes, étirements mollets/tibias périostite",
    )

    assert session.type_seance == SportSessionType.RENFORCEMENT
    assert session.type_seance.value == "Renforcement"
    assert session.distance_km is None
    assert session.km_effort is None or session.km_effort == 0.0
    assert session.vitesse_kmh is None
    assert session.allure_formatted is None
    # 35 min * 7 = 245 de charge RPE
    assert session.charge_rpe == 245


def test_sport_session_create_accepts_optional_distance_for_renforcement():
    """SportSessionCreate doit accepter une séance de renfo sans distance obligatoire."""
    create_payload = SportSessionCreate(
        date=date(2026, 10, 7),
        type_seance=SportSessionType.RENFORCEMENT,
        duree_secondes=30 * 60,
        ressenti_rpe=6,
        notes="PPG mollets",
    )
    assert create_payload.distance_km is None or create_payload.distance_km == 0.0
    assert create_payload.type_seance == SportSessionType.RENFORCEMENT


def test_sport_weekly_summary_with_charge_rpe_total():
    """Vérifie que la synthèse hebdomadaire cumule la charge RPE de la semaine."""
    summary = SportWeeklySummary(
        semaine=41,
        annee=2026,
        nb_seances=3,
        km_total=18.5,
        d_plus_total=120,
        km_effort_total=19.7,
        duree_secondes=6300,
        charge_rpe_totale=520,
        previous_week_km_effort=18.0,
    )
    assert summary.charge_rpe_totale == 520


def test_sport_session_programme_and_remarques_distinction():
    """Vérifie la séparation stricte entre Programme (technique) et Remarques (douleurs/sensations)."""
    session = SportSession(
        date=date(2026, 10, 8),
        semaine=41,
        statut=SportSessionStatus.REALISE,
        type_seance=SportSessionType.FRACTIONNE,
        distance_km=6.5,
        duree_secondes=35 * 60,
        ressenti_rpe=8,
        programme="2km échauffement + 6x400m à 4'15/km + 1km récup",
        remarques="Excellentes sensations sur les 4 premiers blocs, légère raideur mollet à la fin",
    )
    assert session.programme == "2km échauffement + 6x400m à 4'15/km + 1km récup"
    assert session.remarques == "Excellentes sensations sur les 4 premiers blocs, légère raideur mollet à la fin"
    assert "mollet" in session.notes or "6x400m" in session.notes


