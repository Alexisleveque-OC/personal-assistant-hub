"""Tests unitaires et d'intégration TDD pour le Second Cerveau compartimenté (SQLite & LLM)."""
import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import (
    DatabaseManager,
    set_database_manager,
)
from app.core.models import IntentType, NoteCategory
from app.core.intent_parser import IntentParser


@pytest.fixture
def temp_db():
    """Crée une instance isolée de DatabaseManager pour les tests du second cerveau."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    db.init_db()
    set_database_manager(db)
    yield db
    set_database_manager(None)
    if os.path.exists(path):
        os.remove(path)


def test_database_note_crud_operations(temp_db):
    """Vérifie les opérations CRUD de base sur second_brain_notes."""
    # Création d'une note dev_idea
    note_id = temp_db.add_note(
        category="dev_idea",
        content="Implémenter le Push-to-Talk sur la PWA",
        tags=["pwa", "audio"],
    )
    assert isinstance(note_id, int)
    assert note_id > 0

    # Lecture de la note
    note = temp_db.get_note(note_id)
    assert note is not None
    assert note["category"] == "dev_idea"
    assert note["content"] == "Implémenter le Push-to-Talk sur la PWA"
    assert note["tags"] == ["pwa", "audio"]
    assert note["status"] == "active"

    # Ajout d'autres notes pour tester les filtres
    temp_db.add_note(category="bug_report", content="Le bouton micro scintille", tags=["bug"])
    temp_db.add_note(category="thought", content="Tester une nouvelle recette", tags=[])

    # Filtrage par catégorie
    dev_notes = temp_db.get_notes(category="dev_idea")
    assert dev_notes["total"] == 1
    assert dev_notes["items"][0]["content"] == "Implémenter le Push-to-Talk sur la PWA"

    # Mise à jour (status = done)
    updated = temp_db.update_note(note_id, status="done")
    assert updated is True

    note_updated = temp_db.get_note(note_id)
    assert note_updated["status"] == "done"

    # Suppression
    deleted = temp_db.delete_note(note_id)
    assert deleted is True
    assert temp_db.get_note(note_id) is None


def test_intent_parser_local_detects_save_note_segments():
    """Vérifie la détection locale des 5 segments du second cerveau."""
    parser = IntentParser()

    # 1. Dev Idea
    parsed_dev = parser.parse("À dev : ajouter un bouton d'annulation")
    assert parsed_dev.intent == IntentType.SAVE_NOTE
    assert parsed_dev.parameters.get("category") == NoteCategory.DEV_IDEA.value
    assert "ajouter un bouton d'annulation" in parsed_dev.parameters.get("content", "").lower()

    # 2. Bug Report
    parsed_bug = parser.parse("Bug : le graphique RPE ne s'affiche pas")
    assert parsed_bug.intent == IntentType.SAVE_NOTE
    assert parsed_bug.parameters.get("category") == NoteCategory.BUG_REPORT.value
    assert "graphique rpe" in parsed_bug.parameters.get("content", "").lower()

    # 3. Task
    parsed_task = parser.parse("Tâche à faire : appeler le vétérinaire pour le rappel")
    assert parsed_task.intent == IntentType.SAVE_NOTE
    assert parsed_task.parameters.get("category") == NoteCategory.TASK.value

    # 4. Preference
    parsed_pref = parser.parse("Je préfère courir tôt le matin en été")
    assert parsed_pref.intent == IntentType.SAVE_NOTE
    assert parsed_pref.parameters.get("category") == NoteCategory.PREFERENCE.value

    # 5. Thought / Note générique
    parsed_thought = parser.parse("Idée pour plus tard : tester un semi-marathon à l'automne")
    assert parsed_thought.intent == IntentType.SAVE_NOTE
    assert parsed_thought.parameters.get("category") == NoteCategory.THOUGHT.value


def test_intent_parser_local_detects_list_and_delete_notes():
    """Vérifie la détection des commandes de consultation et suppression de notes."""
    parser = IntentParser()

    # Consultation filtrée par idées dev
    parsed_list_dev = parser.parse("Quelles sont mes idées de dev ?")
    assert parsed_list_dev.intent == IntentType.LIST_NOTES
    assert parsed_list_dev.parameters.get("category") == NoteCategory.DEV_IDEA.value

    # Consultation générale
    parsed_list_all = parser.parse("Liste mes notes")
    assert parsed_list_all.intent == IntentType.LIST_NOTES

    # Suppression avec ID
    parsed_del = parser.parse("Supprime la note 5")
    assert parsed_del.intent == IntentType.DELETE_NOTE
    assert parsed_del.parameters.get("note_id") == 5


def test_api_interact_saves_and_lists_notes(temp_db):
    """Vérifie l'interaction de bout en bout via /api/v1/interact."""
    client = TestClient(app)

    # 1. Enregistrement d'une idée dev
    resp_save = client.post(
        "/api/v1/interact",
        json={"query": "À dev : créer un widget Android pour Otis", "session_id": "test-notes"},
    )
    assert resp_save.status_code == 200
    save_data = resp_save.json()
    assert save_data["success"] is True
    assert "noté" in save_data["spoken_response"].lower() or "enregistré" in save_data["spoken_response"].lower()

    # Vérification en base
    notes = temp_db.get_notes(category="dev_idea")
    assert notes["total"] == 1
    assert "widget android" in notes["items"][0]["content"].lower()

    # 2. Consultation des notes
    resp_list = client.post(
        "/api/v1/interact",
        json={"query": "Quelles sont mes idées de dev ?", "session_id": "test-notes"},
    )
    assert resp_list.status_code == 200
    list_data = resp_list.json()
    assert list_data["success"] is True
    assert "widget" in list_data["spoken_response"].lower()


def test_second_brain_rest_endpoints(temp_db):
    """Vérifie les endpoints REST sous /api/v1/second-brain."""
    client = TestClient(app)

    # 1. Création via POST
    payload = {
        "category": "dev_idea",
        "content": "Intégrer Strava via webhook",
        "tags": ["strava", "api"],
    }
    resp = client.post("/api/v1/second-brain/notes", json=payload)
    assert resp.status_code == 201
    created_note = resp.json()
    assert created_note["id"] > 0
    assert created_note["category"] == "dev_idea"
    note_id = created_note["id"]

    # 2. Récupération GET paginée
    resp_get = client.get("/api/v1/second-brain/notes?category=dev_idea")
    assert resp_get.status_code == 200
    notes_page = resp_get.json()
    assert notes_page["total"] == 1
    assert notes_page["items"][0]["content"] == "Intégrer Strava via webhook"

    # 3. Statistiques par segment
    resp_stats = client.get("/api/v1/second-brain/stats")
    assert resp_stats.status_code == 200
    stats = resp_stats.json()
    assert stats["dev_idea"] == 1
    assert stats["bug_report"] == 0

    # 4. Modification PATCH (passage en done)
    resp_patch = client.patch(f"/api/v1/second-brain/notes/{note_id}", json={"status": "done"})
    assert resp_patch.status_code == 200
    assert resp_patch.json()["status"] == "done"

    # 5. Suppression DELETE
    resp_del = client.delete(f"/api/v1/second-brain/notes/{note_id}")
    assert resp_del.status_code == 200
    assert resp_del.json()["success"] is True


def test_dynamic_custom_category_detection_and_stats(temp_db):
    """Vérifie la découverte et la création d'un segment dynamique non prédéfini (ex: voyage)."""
    parser = IntentParser()

    # 1. Détection locale d'un préfixe dynamique "note voyage : ..."
    parsed = parser.parse("Note voyage : penser aux passeports et billets de train")
    assert parsed.intent == IntentType.SAVE_NOTE
    assert parsed.parameters.get("category") == "voyage"
    assert "passeports" in parsed.parameters.get("content", "").lower()

    # 2. Enregistrement de bout en bout via /interact
    client = TestClient(app)
    resp = client.post(
        "/api/v1/interact",
        json={"query": "Note voyage : penser aux passeports et billets de train"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "voyage" in data["spoken_response"].lower()

    # 3. Vérification des stats : le nouveau segment 'voyage' apparaît dynamiquement
    resp_stats = client.get("/api/v1/second-brain/stats")
    assert resp_stats.status_code == 200
    stats = resp_stats.json()
    assert stats.get("voyage") == 1

    # 4. Consultation filtrée sur ce segment dynamique
    resp_notes = client.get("/api/v1/second-brain/notes?category=voyage")
    assert resp_notes.status_code == 200
    notes_data = resp_notes.json()
    assert notes_data["total"] == 1
    assert notes_data["items"][0]["category"] == "voyage"

