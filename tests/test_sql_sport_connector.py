"""Tests unitaires TDD pour le connecteur SqlSportConnector (< 1ms, SQLite unifié)."""
from datetime import date, timedelta
import os
import tempfile
import pytest

from app.core.database import DatabaseManager, set_database_manager
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.connectors.sheets.sport_models import (
    SportSession,
    SportSessionCreate,
    SportSessionPlan,
    SportSessionStatus,
    SportSessionType,
    SportSessionUpdate,
    SportWeeklySummary,
)


@pytest.fixture
def temp_sql_connector():
    """Crée une instance isolée de DatabaseManager et SqlSportConnector."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    db.init_db()
    set_database_manager(db)
    connector = SqlSportConnector(db_manager=db)
    yield connector
    set_database_manager(None)
    if os.path.exists(path):
        os.remove(path)


@pytest.mark.asyncio
async def test_sql_sport_connector_health_and_name(temp_sql_connector):
    """Vérifie le nom du connecteur et son état de santé."""
    assert temp_sql_connector.name == "sqlite_sport"
    assert await temp_sql_connector.is_healthy() is True


def test_sql_sport_connector_log_session_and_get(temp_sql_connector):
    """Vérifie l'enregistrement et la lecture d'une séance terminée."""
    today = date(2026, 10, 8)
    log_data = SportSessionCreate(
        date=today,
        statut=SportSessionStatus.REALISE,
        type_seance=SportSessionType.EF,
        distance_km=10.0,
        denivele_d_plus=50,
        duree_secondes=3600,
        ressenti_rpe=6,
        fc_moyenne=140,
        fc_max=158,
        programme="Endurance fondamentale 10km",
        remarques="Super forme",
    )
    saved = temp_sql_connector.log_session(log_data)
    assert isinstance(saved, SportSession)
    assert saved.date == today
    assert saved.distance_km == 10.0
    assert saved.km_effort == 10.5  # 10 + 50/100
    assert saved.vitesse_kmh == 10.0
    assert saved.allure_formatted == "06:00"
    assert saved.charge_rpe == 360  # 60 min * 6

    # Relecture
    fetched = temp_sql_connector.get_session(today)
    assert fetched is not None
    assert fetched.date == today
    assert fetched.distance_km == 10.0
    assert fetched.ressenti_rpe == 6


def test_sql_sport_connector_plan_session_and_weekly(temp_sql_connector):
    """Vérifie la planification d'une séance unitaire et d'un semainier."""
    mon = date(2026, 10, 12)
    plan1 = SportSessionPlan(
        date=mon,
        type_seance=SportSessionType.EF,
        distance_km_cible=8.0,
        programme="Footing léger 45 min",
        allure_cible="06:15/km",
    )
    p_saved = temp_sql_connector.plan_session(plan1)
    assert p_saved.statut == SportSessionStatus.PLANIFIE
    assert p_saved.type_seance == SportSessionType.EF
    assert p_saved.distance_km == 8.0

    # Semainier
    plans = [
        SportSessionPlan(date=date(2026, 10, 14), type_seance=SportSessionType.FRACTIONNE, programme="6x400m"),
        SportSessionPlan(date=date(2026, 10, 16), type_seance=SportSessionType.RENFORCEMENT, programme="Gainage & mollets"),
    ]
    batch_saved = temp_sql_connector.plan_weekly_sessions(plans)
    assert len(batch_saved) == 2

    # Consultation de la semaine 42
    week_sessions = temp_sql_connector.get_week_sessions(week_num=42, year=2026)
    assert len(week_sessions) == 3


def test_sql_sport_connector_update_session(temp_sql_connector):
    """Vérifie la modification d'une séance existante."""
    target_d = date(2026, 10, 8)
    temp_sql_connector.plan_session(
        SportSessionPlan(date=target_d, type_seance=SportSessionType.EF, programme="Sortie 8km")
    )

    # Mise à jour avec conversion en séance Réalisée et ajout des métriques
    update = SportSessionUpdate(
        statut=SportSessionStatus.REALISE,
        distance_km=8.5,
        duree_secondes=3060,
        ressenti_rpe=7,
        remarques="Un peu lourd sur la fin",
    )
    updated = temp_sql_connector.update_session(target_d, update)
    assert updated.statut == SportSessionStatus.REALISE
    assert updated.distance_km == 8.5
    assert updated.ressenti_rpe == 7
    assert updated.remarques == "Un peu lourd sur la fin"


def test_sql_sport_connector_target_type_and_append_notes(temp_sql_connector):
    """Vérifie la distinction multi-séances par target_type et l'append de remarques."""
    d = date(2026, 10, 10)
    # Deux séances le même jour : une EF et un Renforcement
    temp_sql_connector.db.add_sport_session({
        "date": d.isoformat(),
        "semaine": 41,
        "type_seance": "EF",
        "statut": "Réalisé",
        "distance_km": 10.0,
        "remarques": "Footing matinal",
    })
    temp_sql_connector.db.add_sport_session({
        "date": d.isoformat(),
        "semaine": 41,
        "type_seance": "Renforcement",
        "statut": "Réalisé",
        "remarques": "Séance mollets",
    })

    # Mise à jour spécifique de la séance Renforcement
    update = SportSessionUpdate(
        ressenti_rpe=8,
        remarques="Périostite indolore",
        append_remarques=True,
    )
    updated_renfo = temp_sql_connector.update_session(
        target_date=d,
        updates=update,
        target_type=SportSessionType.RENFORCEMENT,
    )
    assert updated_renfo.type_seance == SportSessionType.RENFORCEMENT
    assert updated_renfo.ressenti_rpe == 8
    assert "Séance mollets | Périostite indolore" in updated_renfo.remarques


def test_sql_sport_connector_plan_session_kwargs(temp_sql_connector):
    """Vérifie la planification directe via arguments kwargs."""
    target_d = date(2026, 10, 15)
    planned = temp_sql_connector.plan_session(
        session_date=target_d,
        type_seance="Fractionné",
        distance_km=10.5,
        programme="10x300m à 3'50/km",
        allure_cible="03:50/km",
    )
    assert planned.statut == SportSessionStatus.PLANIFIE
    assert planned.type_seance == SportSessionType.FRACTIONNE
    assert planned.distance_km == 10.5
    assert planned.programme == "10x300m à 3'50/km"


def test_sql_sport_connector_weekly_summary_and_coaching(temp_sql_connector):
    """Vérifie le calcul automatique du résumé hebdomadaire et du diagnostic sécurité."""
    # Semaine 40 (S-1) : 20 km total
    temp_sql_connector.log_session(
        SportSessionCreate(
            date=date(2026, 9, 30),
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.EF,
            distance_km=20.0,
            denivele_d_plus=0,
            duree_secondes=7200,
            ressenti_rpe=5,
        )
    )

    # Semaine 41 (Semaine en cours) : 22 km course + 1 renfo
    temp_sql_connector.log_session(
        SportSessionCreate(
            date=date(2026, 10, 6),
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.FRACTIONNE,
            distance_km=10.0,
            denivele_d_plus=50,
            duree_secondes=3300,
            ressenti_rpe=8,
        )
    )
    temp_sql_connector.log_session(
        SportSessionCreate(
            date=date(2026, 10, 7),
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.RENFORCEMENT,
            duree_secondes=1800,
            ressenti_rpe=5,
        )
    )
    temp_sql_connector.log_session(
        SportSessionCreate(
            date=date(2026, 10, 8),
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.SORTIE_LONGUE,
            distance_km=12.0,
            denivele_d_plus=100,
            duree_secondes=4500,
            ressenti_rpe=6,
        )
    )

    summary = temp_sql_connector.get_weekly_summary(week_num=41, year=2026)
    assert isinstance(summary, SportWeeklySummary)
    assert summary.nb_seances == 3
    assert summary.km_total == 22.0
    assert summary.nb_renfo == 1
    assert summary.previous_week_km_effort == 20.0
    assert summary.evolution_volume_pct is not None
    # 22 km + 150m D+ = 23.5 km effort vs 20.0 km effort -> +17.5%
    assert summary.km_effort_total == 23.5
    assert summary.evolution_volume_pct == 17.5
    assert "Risque Blessure" in summary.alerte_securite

    # Liste de toutes les synthèses
    all_sums = temp_sql_connector.get_all_summaries(year=2026)
    assert len(all_sums) >= 2


@pytest.mark.asyncio
async def test_sql_sport_connector_execute_action(temp_sql_connector):
    """Vérifie l'exécution d'action via execute_action."""
    today = date(2026, 10, 8)
    temp_sql_connector.plan_session(
        SportSessionPlan(date=today, type_seance=SportSessionType.EF, programme="Test action")
    )
    res = await temp_sql_connector.execute_action("get_session", {"target_date": today.isoformat()})
    assert res is not None
    assert res["type_seance"] == "EF"
