"""Tests unitaires TDD pour le script de migration Sheets -> SQLite et les outils d'export/backup."""
import csv
from datetime import date
import json
import os
import tempfile
from unittest.mock import MagicMock
import pytest

from app.core.database import DatabaseManager, set_database_manager
from app.connectors.sheets.sport_models import (
    SportSession,
    SportSessionStatus,
    SportSessionType,
    SportWeeklySummary,
)
from scripts.migrate_sport_sheets_to_sqlite import migrate_sheets_to_sqlite
from scripts.export_sport_data import export_sport_data


@pytest.fixture
def temp_migration_db():
    """Crée une instance isolée de DatabaseManager pour tester la migration et l'export."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    db.init_db()
    set_database_manager(db)
    yield db
    set_database_manager(None)
    if os.path.exists(path):
        os.remove(path)


def test_migrate_sheets_to_sqlite_success_and_idempotence(temp_migration_db):
    """Vérifie l'aspiration des séances et synthèses depuis un connecteur mock vers SQLite, avec idempotence."""
    mock_connector = MagicMock()

    # Données simulées provenant du Google Sheet
    sample_sessions = [
        SportSession(
            date=date(2026, 9, 28),
            semaine=40,
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.EF,
            distance_km=10.0,
            denivele_d_plus=30,
            duree_secondes=3600,
            ressenti_rpe=6,
            programme="Footing aisé",
            remarques="Nickel",
        ),
        SportSession(
            date=date(2026, 10, 2),
            semaine=40,
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.RENFORCEMENT,
            duree_secondes=1800,
            ressenti_rpe=5,
            programme="Mollets & soléaires",
        ),
    ]

    sample_summaries = [
        SportWeeklySummary(
            semaine=40,
            annee=2026,
            nb_seances=2,
            km_total=10.0,
            d_plus_total=30,
            km_effort_total=10.3,
            duree_secondes=5400,
            charge_rpe_totale=510,
            nb_renfo=1,
            vitesse_moyenne_kmh=10.0,
        )
    ]

    mock_connector.get_all_sessions.return_value = sample_sessions
    mock_connector.get_all_summaries.return_value = sample_summaries

    # 1. Première passe de migration
    report = migrate_sheets_to_sqlite(mock_connector, temp_migration_db, dry_run=False)
    assert report["sessions_migrated"] == 2
    assert report["summaries_migrated"] == 1
    assert len(report["errors"]) == 0

    # Vérification en base SQLite
    db_sessions = temp_migration_db.get_sport_sessions()
    assert len(db_sessions) == 2
    assert db_sessions[0]["distance_km"] == 10.0

    summary_in_db = temp_migration_db.get_sport_weekly_summary(40, 2026)
    assert summary_in_db is not None
    assert summary_in_db["charge_rpe_totale"] == 510

    # 2. Deuxième passe (test d'idempotence : zéro doublon créé)
    report_2 = migrate_sheets_to_sqlite(mock_connector, temp_migration_db, dry_run=False)
    assert report_2["sessions_migrated"] == 2
    db_sessions_after = temp_migration_db.get_sport_sessions()
    assert len(db_sessions_after) == 2  # Toujours 2 séances, aucun doublon !


def test_export_sport_data_json_and_csv(temp_migration_db, tmp_path):
    """Vérifie l'export des données sportives SQLite vers JSON et CSV."""
    # Insertion de données de test en base
    temp_migration_db.add_sport_session({
        "date": "2026-10-08",
        "semaine": 41,
        "statut": "Réalisé",
        "type_seance": "EF",
        "distance_km": 12.0,
        "duree_secondes": 4320,
        "ressenti_rpe": 6,
    })
    temp_migration_db.upsert_sport_weekly_summary({
        "semaine": 41,
        "annee": 2026,
        "nb_seances": 1,
        "km_total": 12.0,
        "d_plus_total": 0,
        "km_effort_total": 12.0,
        "duree_secondes": 4320,
        "charge_rpe_totale": 432,
        "nb_renfo": 0,
    })

    export_dir = str(tmp_path / "backups")
    os.makedirs(export_dir, exist_ok=True)

    result_files = export_sport_data(temp_migration_db, export_dir=export_dir, export_format="all")
    assert "json" in result_files
    assert "sessions_csv" in result_files
    assert "summaries_csv" in result_files

    # 1. Vérification du fichier JSON
    json_path = result_files["json"]
    assert os.path.exists(json_path)
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["sessions_count"] == 1
    assert data["summaries_count"] == 1
    assert data["sessions"][0]["distance_km"] == 12.0

    # 2. Vérification du CSV séances
    sessions_csv_path = result_files["sessions_csv"]
    assert os.path.exists(sessions_csv_path)
    with open(sessions_csv_path, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
    assert len(reader) == 1
    assert reader[0]["date"] == "2026-10-08"

    # 3. Vérification du CSV synthèses
    summaries_csv_path = result_files["summaries_csv"]
    assert os.path.exists(summaries_csv_path)
    with open(summaries_csv_path, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
    assert len(reader) == 1
    assert reader[0]["semaine"] == "41"
