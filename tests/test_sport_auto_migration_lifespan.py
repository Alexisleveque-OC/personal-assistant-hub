"""Tests unitaires pour l'auto-migration des données sportives au démarrage (lifespan)."""
from unittest.mock import MagicMock, patch
import pytest

from app.core.database import DatabaseManager
from app.main import _auto_migrate_sport_sheets


def test_auto_migrate_skips_when_sessions_already_exist(tmp_path):
    """Si des séances existent déjà en base SQLite, aucune migration n'est déclenchée."""
    db_file = str(tmp_path / "test_hub.db")
    db = DatabaseManager(db_path=db_file)
    db.init_db()

    # Insertion d'une séance factice
    db.add_sport_session({
        "date": "2026-10-10",
        "semaine": 41,
        "statut": "Réalisé",
        "type_seance": "EF",
    })

    with patch("app.main.get_database_manager", return_value=db), \
         patch("scripts.migrate_sport_sheets_to_sqlite.migrate_sheets_to_sqlite") as mock_migrate:
        _auto_migrate_sport_sheets(force=True)
        mock_migrate.assert_not_called()


def test_auto_migrate_triggers_when_db_is_empty_and_sheet_id_set(tmp_path):
    """Si la base SQLite est vide et que SPREADSHEET_SPORT_ID est configuré, la migration se lance."""
    db_file = str(tmp_path / "test_hub_empty.db")
    db = DatabaseManager(db_path=db_file)
    db.init_db()

    mock_report = {"sessions_migrated": 14, "summaries_migrated": 4, "errors": []}

    with patch("app.main.get_database_manager", return_value=db), \
         patch("app.main.settings") as mock_settings, \
         patch("app.connectors.sheets.sport_connector.SportConnector") as mock_conn_cls, \
         patch("scripts.migrate_sport_sheets_to_sqlite.migrate_sheets_to_sqlite", return_value=mock_report) as mock_migrate:
        mock_settings.spreadsheet_sport_id = "test_sheet_id_123"
        mock_conn_cls.return_value = MagicMock()

        _auto_migrate_sport_sheets(force=True)

        mock_migrate.assert_called_once()
