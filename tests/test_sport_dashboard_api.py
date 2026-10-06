"""Tests d'intégration API (TDD) pour les endpoints du Dashboard Sport Running (Étape 7.1)."""
from datetime import date, timedelta
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app, set_sport_connector
from app.config import settings
from app.connectors.sheets.sport_connector import SportConnector
from app.connectors.sheets.sport_models import (
    CoachTipLevel,
    DashboardScale,
    SportSession,
    SportSessionStatus,
    SportSessionType,
    SportSessionUpdate,
)

client = TestClient(app)

REF_DATE = date(2026, 10, 7)


@pytest.fixture
def mock_sport_backend():
    """Crée un mock SportConnector complet avec get_all_sessions et update_session."""
    mock_conn = MagicMock(spec=SportConnector)

    s1 = SportSession(
        date=date(2026, 9, 30),
        semaine=40,
        statut=SportSessionStatus.REALISE,
        type_seance=SportSessionType.EF,
        distance_km=5.0,
        duree_secondes=1800,
        ressenti_rpe=5,
        remarques="Sensations légères",
    )
    s2 = SportSession(
        date=REF_DATE,
        semaine=41,
        statut=SportSessionStatus.REALISE,
        type_seance=SportSessionType.EF,
        distance_km=5.2,
        duree_secondes=1820,
        ressenti_rpe=6,
        remarques="Bonne aisance",
    )
    sessions = [s1, s2]

    mock_conn.get_all_sessions.return_value = list(sessions)

    def mock_update(target_date, update_data, target_type=None):
        if target_date != REF_DATE:
            raise ValueError(f"Aucune séance trouvée pour {target_date}")
        if target_type and target_type != SportSessionType.EF:
            raise ValueError(f"Aucune séance de type {target_type} le {target_date}")
        # Met à jour s2
        if isinstance(update_data, dict):
            update_payload = SportSessionUpdate(**update_data)
        else:
            update_payload = update_data
        updated = s2.model_copy()
        if update_payload.ressenti_rpe is not None:
            updated.ressenti_rpe = update_payload.ressenti_rpe
        if update_payload.remarques is not None:
            if update_payload.append_remarques:
                updated.remarques = f"{updated.remarques} | {update_payload.remarques}"
            else:
                updated.remarques = update_payload.remarques
        return updated

    mock_conn.update_session.side_effect = mock_update
    set_sport_connector(mock_conn)
    yield mock_conn
    set_sport_connector(None)


def test_get_sport_today_success(mock_sport_backend):
    """GET /api/v1/sport/today renvoie les séances, les comparaisons et le conseil coach."""
    res = client.get(f"/api/v1/sport/today?date={REF_DATE.isoformat()}")
    assert res.status_code == 200
    data = res.json()
    assert data["date"] == REF_DATE.isoformat()
    assert len(data["seances"]) == 1
    assert data["seances"][0]["type_seance"] == "EF"
    assert len(data["comparisons"]) == 1
    comp = data["comparisons"][0]
    assert comp["previous_session"]["date"] == "2026-09-30"
    assert "coach_tip" in data
    assert data["coach_tip"]["message"] != ""
    assert data["coach_tip"]["niveau"] in ("info", "vigilance", "alerte")
    assert "daily_spotlight" in data


def test_patch_sport_session_success(mock_sport_backend):
    """PATCH /api/v1/sport/session/{date} met à jour le RPE et les remarques."""
    payload = {
        "ressenti_rpe": 8,
        "remarques": "Tibia un peu sensible après le km 4",
        "append_remarques": True,
        "target_type": "EF",
    }
    res = client.patch(f"/api/v1/sport/session/{REF_DATE.isoformat()}", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["session"]["ressenti_rpe"] == 8
    assert "Tibia un peu sensible" in data["session"]["remarques"]


def test_patch_sport_session_not_found(mock_sport_backend):
    """PATCH /api/v1/sport/session/{date} renvoie 404 si la séance n'existe pas."""
    payload = {"ressenti_rpe": 5}
    res = client.patch("/api/v1/sport/session/2026-01-01", json=payload)
    assert res.status_code == 404
    assert "Aucune séance trouvée" in res.json()["detail"]


def test_get_sport_dashboard_week_scale(mock_sport_backend):
    """GET /api/v1/sport/dashboard?scale=week renvoie les totaux et les séries sur 8 semaines."""
    res = client.get(f"/api/v1/sport/dashboard?scale=week&date={REF_DATE.isoformat()}")
    assert res.status_code == 200
    data = res.json()
    assert data["scale"] == "week"
    assert "Semaine 41" in data["label"]
    assert "totals" in data
    assert data["totals"]["nb_seances"] >= 1
    assert len(data["series"]) == 8


def test_get_sport_dashboard_month_and_year_scales(mock_sport_backend):
    """GET /api/v1/sport/dashboard supporte month et year."""
    res_m = client.get(f"/api/v1/sport/dashboard?scale=month&date={REF_DATE.isoformat()}")
    assert res_m.status_code == 200
    assert res_m.json()["scale"] == "month"

    res_y = client.get(f"/api/v1/sport/dashboard?scale=year&date={REF_DATE.isoformat()}")
    assert res_y.status_code == 200
    assert res_y.json()["scale"] == "year"
    assert len(res_y.json()["series"]) == 12


def test_get_sport_dashboard_invalid_scale(mock_sport_backend):
    """Scale inconnue -> 422 validation error."""
    res = client.get("/api/v1/sport/dashboard?scale=quarter")
    assert res.status_code == 422


def test_sport_routes_require_api_key_when_configured(mock_sport_backend, monkeypatch):
    """Vérifie que les endpoints sport sont protégés par la clé d'API si configurée."""
    monkeypatch.setattr(settings, "api_key", "secret123")

    # Sans header -> 401
    res = client.get("/api/v1/sport/today")
    assert res.status_code == 401

    # Avec header -> 200
    res_auth = client.get(f"/api/v1/sport/today?date={REF_DATE.isoformat()}", headers={"X-API-Key": "secret123"})
    assert res_auth.status_code == 200


def test_sport_routes_connector_unavailable_returns_503():
    """Si le connecteur sport est indisponible -> 503 explicite."""
    set_sport_connector(None)
    res = client.get("/api/v1/sport/today")
    assert res.status_code == 503
    assert "Connecteur sport non disponible" in res.json()["detail"]
