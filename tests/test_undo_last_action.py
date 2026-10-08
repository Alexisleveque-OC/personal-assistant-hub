"""Tests unitaires et fonctionnels pour la commande d'annulation immédiate ('undo_last_action')."""
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.models import IntentType
from app.core.intent_parser import IntentParser
from app.core.database import DatabaseManager, set_database_manager
from app.core.dependencies import get_sessions_store, set_meals_connector


@pytest.fixture
def temp_db(tmp_path):
    """Fournit un DatabaseManager isolé sur une base SQLite temporaire."""
    db_file = tmp_path / "test_undo.db"
    manager = DatabaseManager(db_path=str(db_file))
    manager.init_db()
    set_database_manager(manager)
    yield manager
    set_database_manager(None)


@pytest.fixture(autouse=True)
def clean_sessions():
    """Nettoie le store des sessions avant chaque test."""
    store = get_sessions_store()
    store.clear()
    yield
    store.clear()


def test_intent_parser_detects_undo_last_action():
    """Vérifie la détection locale des ordres d'annulation immédiate."""
    parser = IntentParser()

    queries = [
        "annule ma dernière commande",
        "annule ma dernière action",
        "annule ce que tu viens de faire",
        "annule ça",
        "oups annule",
        "reviens en arrière",
        "retour en arrière",
        "undo",
        "annule",
    ]

    for q in queries:
        parsed = parser.parse(q)
        assert parsed.intent == IntentType.UNDO_LAST_ACTION, f"Échec pour query: {q}"


def test_undo_second_brain_save_note(temp_db):
    """Vérifie qu'un 'annule ça' supprime immédiatement la note venant d'être créée."""
    client = TestClient(app)
    session_id = "test-undo-note"

    # 1. Création d'une note
    resp_note = client.post(
        "/api/v1/interact",
        json={"query": "À dev : implémenter le rollback automatique", "session_id": session_id},
    )
    assert resp_note.status_code == 200
    notes = temp_db.get_notes(category="dev_idea")
    assert notes["total"] == 1
    created_note_id = notes["items"][0]["id"]

    # 2. Ordre d'annulation
    resp_undo = client.post(
        "/api/v1/interact",
        json={"query": "Annule ça", "session_id": session_id},
    )
    assert resp_undo.status_code == 200
    data = resp_undo.json()
    assert data["success"] is True
    assert "annulé" in data["spoken_response"].lower()

    # 3. Vérification de la suppression effective en DB
    note_in_db = temp_db.get_note(created_note_id)
    assert note_in_db is None or note_in_db.get("status") == "cancelled"


def test_undo_teach_assistant_rule(temp_db):
    """Vérifie qu'un 'annule' désactive ou supprime la règle d'apprentissage venant d'être formulée."""
    client = TestClient(app)
    session_id = "test-undo-teach"

    # 1. Alexis apprend une règle à Otis
    resp_teach = client.post(
        "/api/v1/interact",
        json={"query": "Quand je dis renfort je veux dire renforcement", "session_id": session_id},
    )
    assert resp_teach.status_code == 200
    learnings = temp_db.get_active_learnings()
    assert len(learnings) == 1
    rule_id = learnings[0]["id"]

    # 2. Ordre d'annulation
    resp_undo = client.post(
        "/api/v1/interact",
        json={"query": "Oups annule ma dernière commande", "session_id": session_id},
    )
    assert resp_undo.status_code == 200
    data = resp_undo.json()
    assert data["success"] is True
    assert "annulé" in data["spoken_response"].lower()

    # 3. Vérification que la règle n'est plus active
    active_learnings = temp_db.get_active_learnings()
    assert len(active_learnings) == 0


def test_undo_shopping_add_item():
    """Vérifie qu'un 'annule' retire le dernier article ajouté à la liste de courses."""
    client = TestClient(app)
    session_id = "test-undo-shop"

    # Mock du connecteur repas / courses
    mock_connector = MagicMock()
    mock_connector.add_shopping_item.return_value = True
    mock_connector.remove_shopping_item.return_value = True
    set_meals_connector(mock_connector)

    try:
        # 1. Ajout d'un article
        resp_add = client.post(
            "/api/v1/interact",
            json={"query": "Ajoute du beurre", "session_id": session_id},
        )
        assert resp_add.status_code == 200
        mock_connector.add_shopping_item.assert_called_once()

        # 2. Ordre d'annulation
        resp_undo = client.post(
            "/api/v1/interact",
            json={"query": "Annule", "session_id": session_id},
        )
        assert resp_undo.status_code == 200
        data = resp_undo.json()
        assert data["success"] is True
        assert "annulé" in data["spoken_response"].lower()

        # 3. Le mock doit avoir appelé remove_shopping_item
        mock_connector.remove_shopping_item.assert_called_once()
    finally:
        set_meals_connector(None)


def test_undo_when_no_recent_action():
    """Vérifie le message prévenant lorsqu'aucune action n'est annulable."""
    client = TestClient(app)
    session_id = "test-undo-empty"

    resp = client.post(
        "/api/v1/interact",
        json={"query": "Reviens en arrière", "session_id": session_id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "aucune action" in data["spoken_response"].lower()
