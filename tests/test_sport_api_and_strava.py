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
    def mock_log_side_effect(session_data):
        if hasattr(session_data, "type_seance") and session_data.type_seance == SportSessionType.RENFORCEMENT:
            return SportSession(
                date=session_data.date or today,
                semaine=(session_data.date or today).isocalendar()[1],
                statut=SportSessionStatus.REALISE,
                type_seance=SportSessionType.RENFORCEMENT,
                distance_km=None,
                duree_secondes=session_data.duree_secondes,
                ressenti_rpe=session_data.ressenti_rpe,
                notes=session_data.notes,
            )
        return SportSession(
            date=today,
            semaine=41,
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.EF,
            distance_km=getattr(session_data, "distance_km", 8.0) or 8.0,
            duree_secondes=getattr(session_data, "duree_secondes", 42 * 60) or 42 * 60,
            denivele_d_plus=getattr(session_data, "denivele_d_plus", 100) or 100,
            ressenti_rpe=getattr(session_data, "ressenti_rpe", 6) or 6,
        )
    connector.log_session.side_effect = mock_log_side_effect

    def mock_update_side_effect(target_date, update_data):
        rpe = getattr(update_data, "ressenti_rpe", None) or (update_data.get("ressenti_rpe") if isinstance(update_data, dict) else 9)
        notes = getattr(update_data, "notes", None) or (update_data.get("notes") if isinstance(update_data, dict) else "")
        return SportSession(
            date=date(2026, 10, 4),
            semaine=40,
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.EF,
            distance_km=10.0,
            duree_secondes=50 * 60,
            ressenti_rpe=rpe,
            notes=notes,
        )
    connector.update_session.side_effect = mock_update_side_effect

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


def test_interact_get_sport_session_speaks_programme_and_remarques(client, mock_sport_connector):
    """Vérifie que la lecture d'une séance énonce à la fois le programme technique et les remarques si présentes."""
    today = date.today()
    mock_sport_connector.get_session.side_effect = None
    mock_sport_connector.get_session.return_value = SportSession(
        date=today,
        semaine=41,
        statut=SportSessionStatus.PLANIFIE,
        type_seance=SportSessionType.RENFORCEMENT,
        programme="30 min PPG gainage et mollets",
        remarques="Attention périostite jambe droite",
    )

    response = client.post("/api/v1/interact", json={"query": "Qu'est-ce que j'ai comme séance aujourd'hui ?"})
    assert response.status_code == 200
    data = response.json()
    spoken = data["spoken_response"]
    assert "Renforcement" in spoken
    assert "30 min PPG gainage et mollets" in spoken
    assert "Remarques : Attention périostite jambe droite" in spoken



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


def test_interact_log_renforcement_speaks_rpe_and_duration(client, mock_sport_connector):
    """Vérifie qu'Otis confirme l'enregistrement d'un renforcement musculaire sans évoquer de distance/allure."""
    response = client.post(
        "/api/v1/interact",
        json={"query": "J'ai fait 30 minutes de renfo, ressenti 7 sur 10"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    spoken = data["spoken_response"]
    assert "renforcement" in spoken.lower() or "renfo" in spoken.lower()
    assert "30" in spoken
    assert "km" not in spoken.lower() or "0 km" not in spoken.lower()


def test_interact_update_sport_session_speaks_confirmation_and_injury_advice(client, mock_sport_connector):
    """Vérifie la mise à jour d'un ressenti à 9 et le conseil de bienveillance d'Otis pour la périostite."""
    response = client.post(
        "/api/v1/interact",
        json={"query": "Otis, modifie le ressenti de ma course de dimanche à 9 sur 10 à cause de ma périostite"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    spoken = data["spoken_response"]
    assert "9" in spoken
    # Conseil coach bienveillant (périostite, repos, glaçage ou vigilance)
    assert any(w in spoken.lower() for w in ["périostite", "repos", "soin", "glaçage", "vigilance", "récup"])


def test_interact_update_sport_session_adds_note_douleur(client, mock_sport_connector):
    """Vérifie l'ajout d'une note de douleur post-séance à J+2."""
    response = client.post(
        "/api/v1/interact",
        json={"query": "Otis, ajoute une note sur ma course de dimanche : douleur au tibia à J+2"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    spoken = data["spoken_response"]
    assert "note" in spoken.lower() or "tibia" in spoken.lower() or "enregistr" in spoken.lower()

