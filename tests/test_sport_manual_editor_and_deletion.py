"""Tests TDD pour l'Étape 3 : Éditeur Manuel de Séances et Bouton de Suppression (PWA).

Couvre :
1. Endpoint DELETE /api/v1/sport/session/{session_id} :
   - Suppression effective de la séance en base SQLite
   - Recalcul automatique de la synthèse hebdomadaire
   - Retour 404 si la séance n'existe pas
2. Endpoint PATCH /api/v1/sport/session/id/{session_id} :
   - Modification chirurgicale des champs bruts (distance, durée, RPE, météo, FC, remarques)
   - Recalcul automatique des champs dérivés (allure, vitesse, charge RPE, km-effort)
   - Retour 404 si ID inconnu
3. Sécurité et intégrité :
   - Impossible de corrompre les métriques calculées
   - Transition propre de statut (ex: Prévu -> Réalisé)
"""
from datetime import date
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import DatabaseManager
from app.core.dependencies import set_database_manager, set_sport_connector
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.connectors.sheets.sport_models import (
    SportSessionCreate,
    SportSessionStatus,
    SportSessionType,
)

client = TestClient(app)
API_HEADERS = {"X-API-Key": "test_api_key"}


@pytest.fixture
def temp_sport_env(tmp_path):
    """Initialise une base SQLite temporaire et un SqlSportConnector actif."""
    db_file = tmp_path / "test_sport_editor.db"
    db_mgr = DatabaseManager(db_path=str(db_file))
    db_mgr.init_db()
    set_database_manager(db_mgr)
    connector = SqlSportConnector(db_mgr)
    set_sport_connector(connector)
    yield db_mgr, connector
    set_database_manager(None)
    set_sport_connector(None)


def test_delete_session_endpoint_removes_session_and_updates_summary(temp_sport_env):
    """Vérifie la suppression d'une séance via son ID et le recalcul de la semaine."""
    db_mgr, connector = temp_sport_env

    # 1. Création de deux séances en semaine 41 (2026-10-08 et 2026-10-10)
    sess1 = connector.log_session(SportSessionCreate(
        date=date(2026, 10, 8),
        statut=SportSessionStatus.REALISE,
        type_seance=SportSessionType.EF,
        distance_km=5.0,
        duree_secondes=1800,
        ressenti_rpe=4,
    ))
    sess2 = connector.log_session(SportSessionCreate(
        date=date(2026, 10, 10),
        statut=SportSessionStatus.REALISE,
        type_seance=SportSessionType.SORTIE_LONGUE,
        distance_km=10.0,
        duree_secondes=3600,
        ressenti_rpe=6,
    ))

    # Vérification initiale : synthèse semaine 41 a 2 séances et 15.0 km
    summary_before = connector.get_weekly_summary(week_num=41, year=2026)
    assert summary_before.nb_seances == 2
    assert summary_before.km_total == 15.0

    # 2. Récupérer l'ID de sess1 dans SQLite
    row1 = db_mgr.get_sport_session_by_date("2026-10-08")
    assert row1 is not None
    sess_id = row1["id"]

    # 3. Appel DELETE /api/v1/sport/session/{sess_id}
    res_del = client.delete(
        f"/api/v1/sport/session/{sess_id}",
        headers=API_HEADERS,
    )
    assert res_del.status_code == 200
    del_data = res_del.json()
    assert del_data["success"] is True
    assert del_data["session_id"] == sess_id

    # 4. Vérification : la séance a disparu de SQLite
    assert db_mgr.get_sport_session_by_id(sess_id) is None
    assert connector.get_session(date(2026, 10, 8)) is None

    # 5. La synthèse de la semaine 41 doit être mise à jour (1 séance, 10.0 km)
    summary_after = connector.get_weekly_summary(week_num=41, year=2026)
    assert summary_after.nb_seances == 1
    assert summary_after.km_total == 10.0


def test_delete_session_endpoint_returns_404_if_not_found(temp_sport_env):
    """Vérifie le retour 404 lors de la tentative de suppression d'une séance inexistante."""
    res = client.delete("/api/v1/sport/session/99999", headers=API_HEADERS)
    assert res.status_code == 404
    assert "introuvable" in res.json().get("detail", "").lower()


def test_patch_session_by_id_endpoint_updates_raw_fields_and_recalculates_metrics(temp_sport_env):
    """Vérifie la mise à jour par ID de champs bruts et le recalcul des valeurs dérivées."""
    db_mgr, connector = temp_sport_env

    # 1. Séance initiale planifiée
    connector.plan_session(
        session_date=date(2026, 10, 15),
        type_seance=SportSessionType.EF,
        distance_km=6.0,
        programme="Footing de base",
    )
    row = db_mgr.get_sport_session_by_date("2026-10-15")
    sess_id = row["id"]
    assert row["statut"] == "Prévu"

    # 2. Modification par ID : passage à Réalisé, saisie durée 36m (2160s), RPE 5, Météo 8, FC
    payload = {
        "statut": "Réalisé",
        "distance_km": 6.2,
        "duree_secondes": 2160,
        "ressenti_rpe": 5,
        "meteo_note": 8,
        "fc_moyenne": 142,
        "fc_max": 160,
        "denivele_d_plus": 45,
        "remarques": "Excellentes sensations sur chemin souple",
    }
    res = client.patch(
        f"/api/v1/sport/session/id/{sess_id}",
        headers=API_HEADERS,
        json=payload,
    )
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["success"] is True
    updated_sess = res_data["session"]

    # Vérification des champs bruts
    assert updated_sess["distance_km"] == 6.2
    assert updated_sess["duree_secondes"] == 2160
    assert updated_sess["ressenti_rpe"] == 5
    assert updated_sess["meteo_note"] == 8
    assert updated_sess["fc_moyenne"] == 142
    assert updated_sess["fc_max"] == 160
    assert updated_sess["denivele_d_plus"] == 45
    assert updated_sess["statut"] == "Réalisé"

    # Vérification des champs calculés automatiquement
    assert updated_sess["allure_formatted"] == "05:48"  # 2160 / 6.2 = 348.38s/km = 05:48
    assert updated_sess["vitesse_kmh"] == 10.33  # 6.2 / (2160/3600) = 10.33 km/h
    assert updated_sess["charge_rpe"] == 180  # (2160 / 60) * 5 = 36 * 5 = 180
    assert updated_sess["km_effort"] == 6.65  # 6.2 + 45/100 = 6.65


def test_patch_session_by_id_returns_404_if_unknown_id(temp_sport_env):
    """Vérifie le retour 404 lors de la tentative de modification d'un ID inexistant."""
    res = client.patch(
        "/api/v1/sport/session/id/99999",
        headers=API_HEADERS,
        json={"distance_km": 10.0},
    )
    assert res.status_code == 404
