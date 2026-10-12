"""Tests unitaires pour l'utilitaire de rapatriement de la base de prod (pull_prod_db)."""
from pathlib import Path
from unittest.mock import MagicMock, patch
import sqlite3
import pytest

from scripts.pull_prod_db import pull_production_database, get_database_summary


def test_get_database_summary(tmp_path):
    """Vérifie le comptage et le résumé des tables SQLite d'une base rapatriée."""
    db_file = tmp_path / "test_summary.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE sport_sessions (id INTEGER PRIMARY KEY, date TEXT);")
    conn.execute("INSERT INTO sport_sessions (date) VALUES ('2026-10-10');")
    conn.execute("CREATE TABLE second_brain_notes (id INTEGER PRIMARY KEY, content TEXT);")
    conn.execute("INSERT INTO second_brain_notes (content) VALUES ('Note 1');")
    conn.commit()
    conn.close()

    summary = get_database_summary(str(db_file))
    assert summary["sport_sessions"] == 1
    assert summary["second_brain_notes"] == 1


def test_pull_production_database_creates_backup(tmp_path):
    """Vérifie qu'un backup .bak est automatiquement créé si la base de destination existe déjà."""
    dest_db = tmp_path / "hub_data.db"
    dest_db.write_text("dummy database content")

    with patch("scripts.pull_prod_db.run_litestream_restore") as mock_restore, \
         patch("scripts.pull_prod_db.get_database_summary", return_value={"sport_sessions": 0}):
        mock_restore.return_value = True

        result = pull_production_database(
            replica_url="gcs://my-bucket/hub_data.db",
            output_path=str(dest_db),
            make_backup=True,
        )

        assert result["success"] is True
        backup_file = tmp_path / "hub_data.db.bak"
        assert backup_file.exists()
        assert backup_file.read_text() == "dummy database content"


def test_run_litestream_restore_atomic_replace(tmp_path):
    """Vérifie que run_litestream_restore restaure dans un fichier temporaire puis remplace la cible."""
    from scripts.pull_prod_db import run_litestream_restore

    dest_db = tmp_path / "hub_data.db"
    dest_db.write_text("old content")

    def fake_subprocess_run(cmd, **kwargs):
        # Litestream restore est appelé avec un chemin temporaire
        # Simuler que litestream a écrit le nouveau contenu dans le fichier de sortie demandé
        out_idx = cmd.index("-o") + 1
        output_file = cmd[out_idx]
        assert output_file.endswith(".restore_tmp")
        Path(output_file).write_text("restored production content")
        res = MagicMock()
        res.returncode = 0
        return res

    with patch("shutil.which", side_effect=lambda bin: "/usr/bin/litestream" if bin == "litestream" else None), \
         patch("subprocess.run", side_effect=fake_subprocess_run):
        success = run_litestream_restore("gcs://my-bucket/hub_data.db", str(dest_db))
        assert success is True
        assert dest_db.read_text() == "restored production content"

