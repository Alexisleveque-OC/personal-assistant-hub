"""Refonte UX (ROADMAP Étape 2, décision du 10/11) : douleur d'une séance en base.

`douleur_intensite` : 0 à 10 (vide = jamais renseignée, 0 = aucune douleur) ; `douleur_zone` : texte court.
Pas de reprise de l'historique : les séances existantes gardent des champs vides."""
import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.connectors.sheets.sport_models import SportSessionCreate, SportSessionUpdate, SportSessionType
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.tools.sport_models import LogSessionArgs, SessionChanges, SessionRow, SessionView
from app.core.database import DatabaseManager
from app.main import app


def test_existing_database_gets_the_pain_columns_without_losing_sessions(tmp_path):
    path = str(tmp_path / "old.db")
    with sqlite3.connect(path) as conn:  # schéma d'avant la refonte
        conn.execute("""CREATE TABLE sport_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, semaine INTEGER NOT NULL,
            statut TEXT NOT NULL DEFAULT 'Prévu', type_seance TEXT NOT NULL DEFAULT 'EF', distance_km REAL,
            denivele_d_plus INTEGER DEFAULT 0, duree_secondes INTEGER, ressenti_rpe INTEGER, fc_moyenne INTEGER,
            fc_max INTEGER, meteo_note INTEGER, programme TEXT DEFAULT '', remarques TEXT DEFAULT '',
            notes TEXT DEFAULT '', allure_cible TEXT, vitesse_cible TEXT, strava_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("INSERT INTO sport_sessions (date, semaine, distance_km) VALUES ('2026-11-09', 46, 7.01)")

    manager = DatabaseManager(db_path=path)
    manager.init_db()
    manager.init_db()  # idempotent

    with sqlite3.connect(path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(sport_sessions)")}
        row = conn.execute("SELECT distance_km, douleur_intensite, douleur_zone FROM sport_sessions").fetchone()
    assert {"douleur_intensite", "douleur_zone"} <= columns
    assert row == (7.01, None, None)


def test_pain_is_saved_read_back_and_can_be_cleared(isolate_sqlite_database):
    connector = SqlSportConnector(db_manager=isolate_sqlite_database)

    saved = connector.log_session(SportSessionCreate(
        date=date(2026, 11, 9), type_seance=SportSessionType.SORTIE_LONGUE, distance_km=7.01,
        douleur_intensite=6, douleur_zone="tibia / genou",
    ))
    assert (saved.douleur_intensite, saved.douleur_zone) == (6, "tibia / genou")

    cleared = connector.update_session_by_id(saved.id, SportSessionUpdate(douleur_intensite=0, douleur_zone=""))
    assert (cleared.douleur_intensite, cleared.douleur_zone) == (0, "")


@pytest.mark.parametrize("value", [-1, 11])
def test_pain_intensity_is_between_0_and_10(value):
    with pytest.raises(ValidationError):
        SportSessionCreate(date=date(2026, 11, 9), douleur_intensite=value)
    with pytest.raises(ValidationError):
        SessionChanges(douleur_intensite=value)


def test_otis_can_log_and_change_the_pain_and_sees_it():
    args = LogSessionArgs(date=date(2026, 11, 9), type_seance="Course", douleur_intensite=4, douleur_zone="mollet")
    assert (args.douleur_intensite, args.douleur_zone) == (4, "mollet")
    assert SessionChanges(douleur_zone="genou").douleur_zone == "genou"
    for model in (LogSessionArgs, SessionChanges, SessionView, SessionRow):
        assert {"douleur_intensite", "douleur_zone"} <= set(model.model_fields), model.__name__


def test_api_creates_and_patches_the_pain(isolate_sqlite_database):
    client = TestClient(app)

    created = client.post("/api/v1/sport/session", json={
        "date": "2026-11-09", "type_seance": "Course", "distance_km": 5, "douleur_intensite": 3, "douleur_zone": "genou",
    })
    assert created.status_code in (200, 201), created.text
    session_id = created.json()["id"] if "id" in created.json() else created.json()["session"]["id"]

    patched = client.patch(f"/api/v1/sport/session/id/{session_id}", json={"douleur_intensite": 7})
    assert patched.status_code == 200, patched.text
    body = patched.json()
    session = body.get("session", body)
    assert (session["douleur_intensite"], session["douleur_zone"]) == (7, "genou")


def test_recent_sessions_in_the_prompt_show_the_pain():
    from app.core.agent.prompt import build_system_prompt
    view = SessionView(id=3, date=date(2026, 11, 9), jour="lundi", statut="Réalisé", type_seance="Course",
                       douleur_intensite=6, douleur_zone="genou")

    assert "douleur 6/10 (genou)" in build_system_prompt(date(2026, 11, 10), [view])
