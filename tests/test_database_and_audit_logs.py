"""Tests unitaires et d'intégration pour le socle de base de données SQLite et le journal conversationnel."""
import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import (
    DatabaseManager,
    get_database_manager,
    set_database_manager,
)


@pytest.fixture
def temp_db():
    """Crée une instance isolée de DatabaseManager avec fichier temporaire."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    db.init_db()
    set_database_manager(db)
    yield db
    set_database_manager(None)
    if os.path.exists(path):
        os.remove(path)


def test_database_initialization_creates_tables_and_wal_mode(temp_db):
    """Vérifie la création des tables et l'activation du mode WAL."""
    with temp_db.get_connection() as conn:
        cursor = conn.cursor()
        
        # Mode WAL
        cursor.execute("PRAGMA journal_mode;")
        mode = cursor.fetchone()[0]
        assert mode.lower() == "wal"

        # Clés étrangères
        cursor.execute("PRAGMA foreign_keys;")
        fk = cursor.fetchone()[0]
        assert fk == 1

        # Vérification des tables créées
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        assert "conversation_logs" in tables
        assert "conversation_feedbacks" in tables
        assert "user_learnings" in tables
        assert "second_brain_notes" in tables


def test_log_conversation_inserts_record_with_metrics(temp_db):
    """Vérifie l'enregistrement d'une interaction dans conversation_logs."""
    log_id = temp_db.log_conversation(
        session_id="session-test-42",
        raw_query="Qu'est-ce qu'on mange ce soir ?",
        intent="get_meal_plan",
        parameters={"period": "soir"},
        spoken_response="Ce soir, c'est Saumon aux poireaux.",
        success=True,
        latency_ms=12.5,
        llm_model="gemini-3.5-flash-lite",
        error_trace=None,
    )
    assert isinstance(log_id, int)
    assert log_id > 0

    log = temp_db.get_conversation_log(log_id)
    assert log is not None
    assert log["session_id"] == "session-test-42"
    assert log["raw_query"] == "Qu'est-ce qu'on mange ce soir ?"
    assert log["intent"] == "get_meal_plan"
    assert log["parameters"] == {"period": "soir"}
    assert log["spoken_response"] == "Ce soir, c'est Saumon aux poireaux."
    assert log["success"] is True
    assert log["latency_ms"] == 12.5
    assert log["llm_model"] == "gemini-3.5-flash-lite"
    assert log["created_at"] is not None


def test_get_conversation_logs_pagination_and_filters(temp_db):
    """Vérifie la pagination et le filtrage des logs conversationnels."""
    # Insérer 3 entrées
    temp_db.log_conversation(
        session_id="s1",
        raw_query="pommes",
        intent="add_shopping_item",
        parameters={"item": "pommes"},
        spoken_response="Ajouté",
        success=True,
        latency_ms=5.0,
    )
    temp_db.log_conversation(
        session_id="s1",
        raw_query="requête inconnue bizarre",
        intent="unknown",
        parameters={},
        spoken_response="Pas compris",
        success=False,
        latency_ms=8.0,
    )
    temp_db.log_conversation(
        session_id="s2",
        raw_query="séance aujourd'hui",
        intent="get_sport_session",
        parameters={},
        spoken_response="8 km EF",
        success=True,
        latency_ms=6.0,
    )

    # Récupération sans filtre
    res = temp_db.get_conversation_logs(limit=2, offset=0)
    assert res["total"] == 3
    assert len(res["items"]) == 2
    assert res["limit"] == 2
    assert res["offset"] == 0

    # Page suivante
    res2 = temp_db.get_conversation_logs(limit=2, offset=2)
    assert len(res2["items"]) == 1

    # Filtre par session_id
    res_s2 = temp_db.get_conversation_logs(session_id="s2")
    assert res_s2["total"] == 1
    assert res_s2["items"][0]["intent"] == "get_sport_session"

    # Filtre par success
    res_fail = temp_db.get_conversation_logs(success=False)
    assert res_fail["total"] == 1
    assert res_fail["items"][0]["intent"] == "unknown"


def test_add_conversation_feedback_and_retrieval(temp_db):
    """Vérifie l'enregistrement et la lecture d'un feedback sur un log."""
    log_id = temp_db.log_conversation(
        session_id="s-feedback",
        raw_query="test",
        intent="small_talk",
        parameters={},
        spoken_response="Bonjour",
        success=True,
        latency_ms=2.0,
    )

    fb_id = temp_db.add_feedback(
        log_id=log_id,
        feedback_type="correction",
        user_note="Tu aurais dû comprendre 3 et non Troyes",
    )
    assert isinstance(fb_id, int)
    assert fb_id > 0

    feedbacks = temp_db.get_feedbacks_for_log(log_id)
    assert len(feedbacks) == 1
    assert feedbacks[0]["feedback_type"] == "correction"
    assert feedbacks[0]["user_note"] == "Tu aurais dû comprendre 3 et non Troyes"


def test_get_conversation_logs_api_endpoint(temp_db):
    """Vérifie l'endpoint HTTP GET /api/v1/system/conversation-logs."""
    temp_db.log_conversation(
        session_id="api-session",
        raw_query="Bonjour",
        intent="small_talk",
        parameters={},
        spoken_response="Salut Alexis !",
        success=True,
        latency_ms=1.5,
    )

    client = TestClient(app)
    response = client.get("/api/v1/system/conversation-logs?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1
    assert data["items"][0]["raw_query"] == "Bonjour"


def test_post_conversation_feedback_api_endpoint(temp_db):
    """Vérifie l'endpoint HTTP POST /api/v1/system/conversation-logs/{id}/feedback."""
    log_id = temp_db.log_conversation(
        session_id="api-fb-session",
        raw_query="RPE à 3",
        intent="log_sport_session",
        parameters={"ressenti_rpe": 3},
        spoken_response="Enregistré",
        success=True,
        latency_ms=3.0,
    )

    client = TestClient(app)
    payload = {
        "feedback_type": "positive",
        "user_note": "Parfaitement compris",
    }
    response = client.post(f"/api/v1/system/conversation-logs/{log_id}/feedback", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert "feedback_id" in data


def test_interact_endpoint_logs_interaction_to_database(temp_db):
    """Vérifie que chaque appel à /api/v1/interact persiste un log dans la base."""
    client = TestClient(app)
    response = client.post(
        "/api/v1/interact",
        json={"query": "bonjour", "session_id": "auto-log-test"},
    )
    assert response.status_code == 200

    logs = temp_db.get_conversation_logs(session_id="auto-log-test")
    assert logs["total"] >= 1
    last_log = logs["items"][0]
    assert last_log["raw_query"] == "bonjour"
    assert last_log["session_id"] == "auto-log-test"
    assert last_log["latency_ms"] >= 0.0
    assert last_log["spoken_response"] != ""
