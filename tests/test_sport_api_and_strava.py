"""Tests unitaires et d'API pour le module Sport Running, Otis interact et Strava."""
from datetime import date, timedelta
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app, set_sport_connector
from app.connectors.sheets.sport_connector import SportConnector
from app.connectors.sheets.sport_models import (
    SportSession,
    SportSessionStatus,
    SportSessionType,
    SportWeeklySummary,
)


@pytest.fixture
def mock_sport_connector():
    """Crée un mock de SportConnector avec des données réalistes."""
    connector = MagicMock(spec=SportConnector)
    today = date.today()

    # Séance planifiée aujourd'hui : Fractionné avec allures
    session_today = SportSession(
        date=today,
        semaine=41,
        statut=SportSessionStatus.PLANIFIE,
        type_seance=SportSessionType.FRACTIONNE,
        distance_km=5.13,
        notes="2km échauffement 6'00/km + 5x300m à 4'30/km avec 100m marche + 1km récup",
    )

    connector.get_session.side_effect = lambda d: session_today if d == today else None
    connector.get_weekly_summary.return_value = SportWeeklySummary(
        semaine=40,
        annee=2026,
        nb_seances=2,
        km_total=10.13,
        d_plus_total=0,
        km_effort_total=10.13,
        duree_secondes=3498,  # 58m18s
        previous_week_km_effort=None,
    )
    connector.log_session.return_value = SportSession(
        date=today,
        semaine=41,
        statut=SportSessionStatus.REALISE,
        type_seance=SportSessionType.EF,
        distance_km=8.0,
        duree_secondes=42 * 60,
        denivele_d_plus=100,
        ressenti_rpe=6,
    )
    return connector


@pytest.fixture
def client(mock_sport_connector):
    """Client de test FastAPI avec injection du mock SportConnector."""
    set_sport_connector(mock_sport_connector)
    yield TestClient(app)
    set_sport_connector(None)


def test_interact_get_sport_session_returns_planned_fractionne_details(client):
    """Vérifie que la demande de séance renvoie les détails complets du fractionné et des allures."""
    response = client.post("/api/v1/interact", json={"query": "Qu'est-ce que j'ai comme séance aujourd'hui ?"})
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    spoken = data["spoken_response"]
    assert "Fractionné" in spoken
    assert "5,13 km" in spoken or "5.13" in spoken
    assert "4'30" in spoken or "échauffement" in spoken


def test_interact_get_sport_session_rest_day_when_empty(client, mock_sport_connector):
    """Quand aucune séance n'est planifiée, Otis répond que c'est une journée de repos."""
    mock_sport_connector.get_session.side_effect = None
    mock_sport_connector.get_session.return_value = None

    response = client.post("/api/v1/interact", json={"query": "C'est quoi ma séance aujourd'hui ?"})
    assert response.status_code == 200
    data = response.json()

    spoken = data["spoken_response"]
    assert "repos" in spoken.lower() or "rien" in spoken.lower()


def test_interact_log_sport_session_records_and_speaks_stats(client, mock_sport_connector):
    """Vérifie que l'enregistrement d'une course terminée confirme l'allure et les km."""
    response = client.post(
        "/api/v1/interact",
        json={"query": "J'ai couru 8 km en 42 minutes avec 100m de dénivelé"},
    )
    assert response.status_code == 200
    data = response.json()

    spoken = data["spoken_response"]
    assert "8" in spoken
    assert "42" in spoken or "allure" in spoken.lower()


def test_interact_get_sport_weekly_summary_speaks_volume_and_10_percent_limit(client):
    """Vérifie que le bilan hebdo énonce le cumul et la recommandation des 10% d'Otis."""
    response = client.post(
        "/api/v1/interact",
        json={"query": "J'en suis à combien de kilomètres cette semaine ?"},
    )
    assert response.status_code == 200
    data = response.json()

    spoken = data["spoken_response"]
    assert "10,13" in spoken or "10.13" in spoken or "10" in spoken
    assert "11" in spoken or "10%" in spoken or "conseille" in spoken.lower()


def test_strava_webhook_challenge(client):
    """Vérifie la réponse au challenge Strava pour l'enregistrement du webhook."""
    params = {
        "hub.mode": "subscribe",
        "hub.challenge": "strava_challenge_code_123",
        "hub.verify_token": "otis_strava_secret",
    }
    response = client.get("/api/v1/integrations/strava/webhook", params=params)
    assert response.status_code == 200
    data = response.json()
    assert data["hub.challenge"] == "strava_challenge_code_123"


def test_strava_sync_activity_endpoint(client, mock_sport_connector):
    """Vérifie que l'ingestion d'une activité Strava crée/met à jour la séance dans Google Sheets."""
    strava_payload = {
        "id": "1234567890",
        "name": "Course du midi",
        "type": "Run",
        "distance": 6200.0,  # 6.2 km en mètres
        "moving_time": 1980,  # 33 minutes en secondes
        "total_elevation_gain": 45.0,  # 45m de D+
        "start_date": "2026-10-06T12:30:00Z",
    }
    response = client.post("/api/v1/sport/sync-activity", json=strava_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["distance_km"] == 6.2
