"""Test d'Intégration End-to-End (E2E) pour la Phase 6.5 : Migration Sport vers SQLite unifié.

Valide l'ensemble du cycle fonctionnel de bout en bout :
1. Initialisation de la base SQLite locale WAL.
2. Planification d'une séance future via interaction vocale / NLU.
3. Consultation vocale avec oralisation naturelle et accords verbaux.
4. Enregistrement d'une course terminée (running) avec calculs physiologiques instantanés (allure, km-effort, charge RPE).
5. Enregistrement d'une séance de renforcement avec tolérance lexicale (« renfort » / « muscu »).
6. Résolution temporelle dynamique (« ma dernière séance », « ma dernière séance de muscu »).
7. Modification orale avec infinitif et oralisation chaleureuse.
8. Consultation du dashboard REST /api/v1/sport/today et de la synthèse hebdomadaire.
9. Export et backup de secours (JSON et CSV).
"""
from datetime import date, timedelta
import os
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import DatabaseManager, set_database_manager, get_database_manager
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.dependencies import set_sport_connector
from app.connectors.sheets.sport_models import SportSessionStatus, SportSessionType
from scripts.export_sport_data import export_sport_data


client = TestClient(app)


def test_e2e_sport_complete_lifecycle(tmp_path):
    """Exécute le cycle complet End-to-End du module Sport sous SQLite."""
    # 1. Initialisation base SQLite isolée
    db_file = str(tmp_path / "hub_sport_e2e.db")
    db_manager = DatabaseManager(db_path=db_file)
    db_manager.init_db()

    sql_connector = SqlSportConnector(db_manager=db_manager)

    old_db = get_database_manager()
    set_database_manager(db_manager)
    set_sport_connector(sql_connector)

    try:
        today = date.today()
        tomorrow = today + timedelta(days=1)

        # 2. Planification future via l'API universelle d'interaction (/api/v1/interact)
        res_plan = client.post(
            "/api/v1/interact",
            json={"query": "planifier un footing pour demain"},
        )
        assert res_plan.status_code == 200
        data_plan = res_plan.json()
        assert data_plan["success"] is True
        assert "planifié" in data_plan["spoken_response"].lower()
        assert "demain" in data_plan["spoken_response"].lower()

        # Vérification en base SQLite
        planned_session = sql_connector.get_session(tomorrow)
        assert planned_session is not None
        assert planned_session.statut == SportSessionStatus.PLANIFIE
        assert planned_session.type_seance == SportSessionType.EF

        # 3. Consultation vocale pour demain (sans 'Pour aujourd'hui')
        res_get_tomorrow = client.post(
            "/api/v1/interact",
            json={"query": "c'est quoi ma séance de demain"},
        )
        assert res_get_tomorrow.status_code == 200
        data_tomorrow = res_get_tomorrow.json()
        assert "Pour demain" in data_tomorrow["spoken_response"]
        assert "vous avez une séance de EF" in data_tomorrow["spoken_response"]
        assert "Pour aujourd'hui" not in data_tomorrow["spoken_response"]

        # 4. Enregistrement d'une course terminée (Running 10 km en 50 min, ressenti 7)
        res_log_run = client.post(
            "/api/v1/interact",
            json={"query": "j'ai couru 10 km en 50 minutes ressenti 7"},
        )
        assert res_log_run.status_code == 200
        data_log_run = res_log_run.json()
        assert data_log_run["success"] is True
        assert "10" in data_log_run["spoken_response"]
        assert "50 minutes" in data_log_run["spoken_response"]

        # Vérification des calculs physiologiques instantanés
        today_session = sql_connector.get_session(today)
        assert today_session is not None
        assert today_session.statut == SportSessionStatus.REALISE
        assert today_session.distance_km == 10.0
        assert today_session.duree_secondes == 3000
        assert today_session.allure_formatted == "05:00"
        assert today_session.vitesse_kmh == 12.0
        assert today_session.km_effort == 10.0
        assert today_session.charge_rpe == 350  # (3000 // 60) * 7 = 50 * 7 = 350

        # 5. Enregistrement d'une séance de renforcement avec tolérance lexicale (« renfort »)
        res_log_renfo = client.post(
            "/api/v1/interact",
            json={"query": "enregistre 30 min de renfort ressenti 6"},
        )
        assert res_log_renfo.status_code == 200
        data_log_renfo = res_log_renfo.json()
        assert data_log_renfo["success"] is True
        assert "renforcement" in data_log_renfo["spoken_response"].lower()

        # 6. Résolution sémantique temporelle de « ma dernière séance »
        res_last = client.post(
            "/api/v1/interact",
            json={"query": "c'est quoi ma dernière séance ?"},
        )
        assert res_last.status_code == 200
        data_last = res_last.json()
        assert data_last["success"] is True
        assert "dernière séance" in data_last["spoken_response"].lower()

        # Consultation ciblée par lexique « mon dernier renfo »
        res_last_renfo = client.post(
            "/api/v1/interact",
            json={"query": "rappelle-moi mon dernier renfo"},
        )
        assert res_last_renfo.status_code == 200
        data_last_renfo = res_last_renfo.json()
        assert "Renforcement" in data_last_renfo["spoken_response"]

        # 7. Modification orale avec infinitif et oralisation chaleureuse
        res_update = client.post(
            "/api/v1/interact",
            json={"query": "modifier ma séance d'aujourd'hui ressenti à 8"},
        )
        assert res_update.status_code == 200
        data_update = res_update.json()
        assert data_update["success"] is True
        assert "mis à jour" in data_update["spoken_response"]
        assert "8/10" in data_update["spoken_response"]

        # 8. Consultation de l'endpoint Dashboard REST (/api/v1/sport/today)
        res_dashboard = client.get("/api/v1/sport/today")
        assert res_dashboard.status_code == 200
        dash_data = res_dashboard.json()
        assert dash_data["date"] == today.isoformat()
        assert len(dash_data["seances"]) >= 1
        assert "coach_tip" in dash_data

        # Consultation de la synthèse hebdomadaire
        iso_cal = today.isocalendar()
        summary = sql_connector.get_weekly_summary(week_num=iso_cal[1], year=iso_cal[0])
        assert summary.nb_seances >= 1
        assert summary.km_effort_total >= 10.0
        assert summary.charge_rpe_totale > 0

        # 9. Export et sauvegarde de secours (JSON / CSV)
        export_dir = str(tmp_path / "exports")
        created = export_sport_data(db_manager=db_manager, export_dir=export_dir)
        assert "json" in created
        assert "sessions_csv" in created
        assert os.path.exists(created["json"])
        assert os.path.exists(created["sessions_csv"])
        assert os.path.getsize(created["json"]) > 0
        assert os.path.getsize(created["sessions_csv"]) > 0

    finally:
        set_database_manager(old_db)
        set_sport_connector(None)
