"""Tests unitaires pour l'Étape 6 : Bascule Globale vers SqlSportConnector par défaut."""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.core.dependencies import (
    get_sport_connector,
    set_sport_connector,
)
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.database import get_database_manager


client = TestClient(app)


def test_get_sport_connector_returns_sql_sport_connector_by_default(tmp_path):
    """Vérifie que la dépendance get_sport_connector injecte SqlSportConnector par défaut sans SPREADSHEET_SPORT_ID."""
    # Réinitialiser à UNSET pour tester la fabrication par défaut
    import app.core.dependencies as deps
    prev_connector = deps._sport_connector
    prev_error = deps._sport_connector_error

    try:
        deps._sport_connector = "UNSET"
        deps._sport_connector_error = None

        # S'assurer que SPREADSHEET_SPORT_ID est vide
        with patch.object(settings, "spreadsheet_sport_id", ""):
            connector = get_sport_connector()
            assert connector is not None
            assert isinstance(connector, SqlSportConnector)
            assert connector.name == "sqlite_sport"
    finally:
        deps._sport_connector = prev_connector
        deps._sport_connector_error = prev_error


def test_sport_today_endpoint_uses_sql_sport_connector(tmp_path):
    """Vérifie que l'endpoint /api/v1/sport/today répond avec succès via SqlSportConnector sans Google Sheets."""
    db = get_database_manager()
    sql_conn = SqlSportConnector(db_manager=db)

    set_sport_connector(sql_conn)
    try:
        resp = client.get("/api/v1/sport/today")
        assert resp.status_code == 200
        data = resp.json()
        assert "date" in data
        assert "seances" in data
        assert "coach_tip" in data
    finally:
        set_sport_connector(None)
