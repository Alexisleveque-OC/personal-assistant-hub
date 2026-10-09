"""Tests unitaires TDD pour la persistance SQLite du module Sport dans DatabaseManager."""
import os
import tempfile
import pytest

from app.core.database import DatabaseManager, set_database_manager


@pytest.fixture
def temp_db():
    """Crée une instance isolée de DatabaseManager pour les tests sport."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    db.init_db()
    set_database_manager(db)
    yield db
    set_database_manager(None)
    if os.path.exists(path):
        os.remove(path)


def test_database_sport_session_crud(temp_db):
    """Vérifie la création, lecture, mise à jour et suppression d'une séance dans sport_sessions."""
    # 1. Insertion
    session_data = {
        "date": "2026-10-08",
        "semaine": 41,
        "statut": "Réalisé",
        "type_seance": "EF",
        "distance_km": 10.5,
        "denivele_d_plus": 45,
        "duree_secondes": 3600,
        "ressenti_rpe": 6,
        "fc_moyenne": 142,
        "fc_max": 160,
        "programme": "Footing endurance fondamentale",
        "remarques": "Bonnes sensations, aucune douleur tibiale",
    }
    session_id = temp_db.add_sport_session(session_data)
    assert isinstance(session_id, int)
    assert session_id > 0

    # 2. Lecture par ID et par Date
    session = temp_db.get_sport_session_by_id(session_id)
    assert session is not None
    assert session["date"] == "2026-10-08"
    assert session["distance_km"] == 10.5
    assert session["ressenti_rpe"] == 6
    assert session["type_seance"] == "EF"
    assert session["statut"] == "Réalisé"

    by_date = temp_db.get_sport_session_by_date("2026-10-08")
    assert by_date is not None
    assert by_date["id"] == session_id

    # 3. Mise à jour
    updated = temp_db.update_sport_session(session_id, {"ressenti_rpe": 7, "remarques": "Légère fatigue en fin"})
    assert updated is True
    session_after_update = temp_db.get_sport_session_by_id(session_id)
    assert session_after_update["ressenti_rpe"] == 7
    assert session_after_update["remarques"] == "Légère fatigue en fin"

    # 4. Suppression
    assert temp_db.delete_sport_session(session_id) is True
    assert temp_db.get_sport_session_by_id(session_id) is None


def test_database_sport_session_filters_and_last_session(temp_db):
    """Vérifie les requêtes avec filtres (semaine, type, date) et la résolution de dernière séance."""
    # Insertion de plusieurs séances
    s1 = temp_db.add_sport_session({
        "date": "2026-10-01",
        "semaine": 40,
        "statut": "Réalisé",
        "type_seance": "EF",
        "distance_km": 8.0,
        "duree_secondes": 3000,
        "ressenti_rpe": 5,
    })
    s2 = temp_db.add_sport_session({
        "date": "2026-10-03",
        "semaine": 40,
        "statut": "Réalisé",
        "type_seance": "Renforcement",
        "duree_secondes": 1800,
        "ressenti_rpe": 6,
    })
    s3 = temp_db.add_sport_session({
        "date": "2026-10-05",
        "semaine": 41,
        "statut": "Réalisé",
        "type_seance": "Fractionné",
        "distance_km": 10.0,
        "duree_secondes": 3300,
        "ressenti_rpe": 8,
    })
    s4 = temp_db.add_sport_session({
        "date": "2026-10-12",
        "semaine": 42,
        "statut": "Prévu",
        "type_seance": "Sortie Longue",
        "distance_km": 15.0,
    })

    # Filtre par semaine
    week_40_sessions = temp_db.get_sport_sessions(week=40)
    assert len(week_40_sessions) == 2
    assert {s["id"] for s in week_40_sessions} == {s1, s2}

    # Filtre par type
    renfo_sessions = temp_db.get_sport_sessions(session_type="Renforcement")
    assert len(renfo_sessions) == 1
    assert renfo_sessions[0]["id"] == s2

    # Filtre par plage de dates
    range_sessions = temp_db.get_sport_sessions(start_date="2026-10-02", end_date="2026-10-06")
    assert len(range_sessions) == 2
    assert [s["id"] for s in range_sessions] == [s2, s3]

    # Dernière séance réalisée (tous types)
    last_realised = temp_db.get_last_sport_session(status="Réalisé")
    assert last_realised is not None
    assert last_realised["id"] == s3
    assert last_realised["date"] == "2026-10-05"

    # Dernier renforcement réalisé
    last_renfo = temp_db.get_last_sport_session(session_type="Renforcement", status="Réalisé")
    assert last_renfo is not None
    assert last_renfo["id"] == s2

    # Dernière séance prévue
    last_prevu = temp_db.get_last_sport_session(status="Prévu")
    assert last_prevu is not None
    assert last_prevu["id"] == s4


def test_database_sport_weekly_summaries_crud_and_upsert(temp_db):
    """Vérifie l'upsert, la lecture et la suppression des synthèses hebdomadaires."""
    summary_data = {
        "semaine": 40,
        "annee": 2026,
        "nb_seances": 3,
        "km_total": 25.5,
        "d_plus_total": 120,
        "km_effort_total": 26.7,
        "duree_secondes": 8100,
        "charge_rpe_totale": 850,
        "nb_renfo": 1,
        "previous_week_km_effort": 24.0,
        "vitesse_moyenne_kmh": 11.3,
        "previous_week_vitesse_kmh": 11.0,
        "previous_week_charge_rpe": 800,
        "duree_course_secondes": 6300,
    }

    # 1. Insertion
    sum_id = temp_db.upsert_sport_weekly_summary(summary_data)
    assert isinstance(sum_id, int)
    assert sum_id > 0

    # 2. Lecture
    retrieved = temp_db.get_sport_weekly_summary(semaine=40, annee=2026)
    assert retrieved is not None
    assert retrieved["km_total"] == 25.5
    assert retrieved["nb_renfo"] == 1
    assert retrieved["vitesse_moyenne_kmh"] == 11.3

    # 3. Upsert (mise à jour sur conflit de semaine et annee)
    summary_data["km_total"] = 30.0
    summary_data["nb_seances"] = 4
    updated_id = temp_db.upsert_sport_weekly_summary(summary_data)
    assert updated_id == sum_id

    updated = temp_db.get_sport_weekly_summary(semaine=40, annee=2026)
    assert updated["km_total"] == 30.0
    assert updated["nb_seances"] == 4

    # 4. Liste de toutes les synthèses
    all_sums = temp_db.get_all_sport_weekly_summaries(annee=2026)
    assert len(all_sums) == 1
    assert all_sums[0]["semaine"] == 40

    # 5. Suppression
    assert temp_db.delete_sport_weekly_summary(semaine=40, annee=2026) is True
    assert temp_db.get_sport_weekly_summary(semaine=40, annee=2026) is None


def test_database_sport_session_validation(temp_db):
    """Vérifie que l'insertion sans date lève une ValueError."""
    with pytest.raises(ValueError, match="date"):
        temp_db.add_sport_session({"semaine": 40})
