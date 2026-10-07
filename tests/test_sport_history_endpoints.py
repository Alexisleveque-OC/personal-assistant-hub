"""Tests unitaires pour les endpoints d'historique des séances et des semaines (Étape 2)."""
from datetime import date, timedelta
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.core.dependencies import set_sport_connector
from app.connectors.sheets.sport_models import (
    SportSession,
    SportSessionStatus,
    SportSessionType,
    SportWeeklySummary,
)
from app.connectors.sheets.sport_connector import SportConnector

client = TestClient(app)


def _build_sample_sessions():
    """Génère un échantillon de séances de test avec différentes dates, types et statuts."""
    base_date = date(2026, 10, 1)
    s1 = SportSession(
        date=base_date,
        semaine=40,
        statut=SportSessionStatus.REALISE,
        type_seance=SportSessionType.EF,
        distance_km=10.0,
        duree_secondes=3600,
        denivele_d_plus=50,
        ressenti_rpe=6,
        fc_moyenne=145,
        programme="Endurance fondamentale 10 km",
        remarques="Bonnes sensations",
    )
    s2 = SportSession(
        date=base_date + timedelta(days=2),
        semaine=40,
        statut=SportSessionStatus.REALISE,
        type_seance=SportSessionType.RENFORCEMENT,
        distance_km=None,
        duree_secondes=1800,
        denivele_d_plus=0,
        ressenti_rpe=7,
        programme="PPG mollets et gainage",
        remarques="Légère fatigue tibias",
    )
    s3 = SportSession(
        date=base_date + timedelta(days=4),
        semaine=41,
        statut=SportSessionStatus.PLANIFIE,
        type_seance=SportSessionType.FRACTIONNE,
        distance_km=8.5,
        duree_secondes=3000,
        denivele_d_plus=30,
        programme="10x 400m à VMA",
    )
    return [s1, s2, s3]


def test_get_sport_sessions_endpoint_returns_chronological_list():
    """Vérifie que GET /api/v1/sport/sessions retourne les séances triées avec pagination."""
    mock_connector = MagicMock()
    mock_connector.get_all_sessions.return_value = _build_sample_sessions()
    set_sport_connector(mock_connector)

    headers = {"X-API-Key": settings.api_key} if settings.api_key else {}
    # Tri descendant par défaut
    response = client.get("/api/v1/sport/sessions", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert "sessions" in data
    assert "total" in data
    assert data["total"] == 3
    sessions = data["sessions"]
    # Vérifier l'ordre antichronologique (s3 le 5 oct, s2 le 3 oct, s1 le 1er oct)
    assert sessions[0]["date"] == "2026-10-05"
    assert sessions[1]["date"] == "2026-10-03"
    assert sessions[2]["date"] == "2026-10-01"


def test_get_sport_sessions_endpoint_filters_by_status_and_type():
    """Vérifie le filtrage par statut et par type de séance."""
    mock_connector = MagicMock()
    mock_connector.get_all_sessions.return_value = _build_sample_sessions()
    set_sport_connector(mock_connector)

    headers = {"X-API-Key": settings.api_key} if settings.api_key else {}

    # Filtrer uniquement les séances réalisées
    res_realise = client.get("/api/v1/sport/sessions?statut=Réalisé", headers=headers)
    assert res_realise.status_code == 200
    data_realise = res_realise.json()
    assert data_realise["total"] == 2
    assert all(s["statut"] == "Réalisé" for s in data_realise["sessions"])

    # Filtrer uniquement le renforcement
    res_renfo = client.get("/api/v1/sport/sessions?type_seance=Renforcement", headers=headers)
    assert res_renfo.status_code == 200
    data_renfo = res_renfo.json()
    assert data_renfo["total"] == 1
    assert data_renfo["sessions"][0]["type_seance"] == "Renforcement"


def test_get_sport_summaries_endpoint_with_embedded_sessions():
    """Vérifie que GET /api/v1/sport/summaries retourne les synthèses de semaines avec les séances imbriquées."""
    mock_connector = MagicMock()
    sum_s40 = SportWeeklySummary(
        semaine=40,
        annee=2026,
        nb_seances=2,
        km_total=10.0,
        d_plus_total=50,
        km_effort_total=10.5,
        duree_secondes=5400,
        charge_rpe_totale=570,
        nb_renfo=1,
    )
    mock_connector.get_all_summaries.return_value = [sum_s40]
    # Deux séances rattachées à S40
    sample_sessions = _build_sample_sessions()
    mock_connector.get_week_sessions.return_value = [sample_sessions[0], sample_sessions[1]]
    set_sport_connector(mock_connector)

    headers = {"X-API-Key": settings.api_key} if settings.api_key else {}
    response = client.get("/api/v1/sport/summaries?include_sessions=true", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert "summaries" in data
    assert "total" in data
    assert data["total"] == 1
    first_summary = data["summaries"][0]
    assert first_summary["summary"]["semaine"] == 40
    assert "seances" in first_summary
    assert len(first_summary["seances"]) == 2
    assert first_summary["seances"][0]["type_seance"] == "EF"


def test_connector_get_all_summaries_parses_synthese_worksheet():
    """Vérifie que connector.get_all_summaries parcourt Synthese_Hebdo ou calcule les semaines."""
    connector = SportConnector.__new__(SportConnector)
    connector._synthese_cache = None
    connector._synthese_cache_time = 0.0
    connector._cache_ttl_seconds = 180

    ws_syn_mock = MagicMock()
    # Entêtes et 2 semaines de synthèse
    rows = [
        ["Semaine", "Année", "Nb séances", "Km total", "D+ total", "Km-effort total", "Durée", "Allure moyenne", "Vitesse moyenne", "Charge RPE"],
        ["40", "2026", "3", "25.0", "150", "26.5", "02:30:00", "06:00", "10.0", "420"],
        ["39", "2026", "2", "18.0", "100", "19.0", "01:50:00", "06:07", "9.8", "310"],
    ]
    ws_syn_mock.get_all_values.return_value = rows
    connector._get_synthese_worksheet = MagicMock(return_value=ws_syn_mock)
    connector.get_week_sessions = MagicMock(return_value=[])

    summaries = connector.get_all_summaries()

    assert len(summaries) == 2
    # Tri par défaut descendant
    assert summaries[0].semaine == 40
    assert summaries[0].km_total == 25.0
    assert summaries[1].semaine == 39
    assert summaries[1].km_total == 18.0
