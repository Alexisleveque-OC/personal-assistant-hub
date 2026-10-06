"""Tests d'intégration API pour le module de gamification et badges sportifs."""
from datetime import date
from typing import List
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.connectors.sheets.sport_connector import SportConnector
from app.connectors.sheets.sport_models import (
    SportGamificationSummary,
    SportSession,
    SportSessionStatus,
    SportSessionType,
)
from app.main import app, set_sport_connector

client = TestClient(app)


def _mock_session(date_str: str, dist: float = 10.0, d_plus: int = 150) -> SportSession:
    d = date.fromisoformat(date_str)
    return SportSession(
        date=d,
        semaine=d.isocalendar()[1],
        statut=SportSessionStatus.REALISE,
        type_seance=SportSessionType.EF,
        distance_km=dist,
        duree_secondes=3600,
        denivele_d_plus=d_plus,
        ressenti_rpe=5,
        remarques="Super séance à la fraîche",
    )


def test_get_sport_gamification_endpoint_success():
    """Vérifie que GET /api/v1/sport/gamification retourne les trophées, records et anecdotes."""
    mock_connector = MagicMock(spec=SportConnector)
    sessions = [
        _mock_session("2026-10-01", dist=25.0, d_plus=200),
        _mock_session("2026-10-02", dist=30.0, d_plus=250),  # 55 km total
    ]
    mock_connector.get_all_sessions.return_value = sessions
    set_sport_connector(mock_connector)

    try:
        response = client.get("/api/v1/sport/gamification")
        assert response.status_code == 200
        data = response.json()

        assert "badges" in data
        assert "personal_records" in data
        assert "fun_facts" in data
        assert "imminent_milestones" in data
        assert data["unlocked_count"] >= 1
        assert data["total_badges"] > 0

        # Badges débloqués
        unlocked_ids = [b["id"] for b in data["badges"] if b["is_unlocked"]]
        assert "dist_10k" in unlocked_ids
        assert "dist_marathon" in unlocked_ids
    finally:
        set_sport_connector(None)


def test_get_sport_gamification_requires_api_key_when_configured(monkeypatch):
    """Vérifie le rejet 401 si clé d'API requise et non fournie."""
    monkeypatch.setattr(settings, "api_key", "secret_game_key_123")

    mock_connector = MagicMock(spec=SportConnector)
    mock_connector.get_all_sessions.return_value = []
    set_sport_connector(mock_connector)

    try:
        # Sans header -> 401
        resp_no_key = client.get("/api/v1/sport/gamification")
        assert resp_no_key.status_code == 401

        # Avec header correct -> 200
        resp_auth = client.get(
            "/api/v1/sport/gamification",
            headers={"X-API-Key": "secret_game_key_123"},
        )
        assert resp_auth.status_code == 200
    finally:
        set_sport_connector(None)


def test_get_sport_gamification_connector_unavailable_returns_503():
    """Vérifie le retour 503 si le connecteur n'est pas initialisé."""
    set_sport_connector(None)

    response = client.get("/api/v1/sport/gamification")
    assert response.status_code == 503
    assert "non disponible" in response.json()["detail"]
