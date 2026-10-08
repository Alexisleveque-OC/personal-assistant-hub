"""Tests unitaires et d'intégration TDD pour l'auto-apprentissage vocal d'Otis (TEACH_ASSISTANT)."""
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import (
    DatabaseManager,
    set_database_manager,
)
from app.core.models import IntentType, ParsedIntent
from app.core.intent_parser import IntentParser
from app.core.llm.nlu_service import GeminiNLUService


@pytest.fixture
def temp_db():
    """Crée une instance isolée de DatabaseManager pour les tests d'apprentissage."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    db.init_db()
    set_database_manager(db)
    yield db
    set_database_manager(None)
    if os.path.exists(path):
        os.remove(path)


def test_database_learnings_crud(temp_db):
    """Vérifie les opérations CRUD sur la table user_learnings."""
    # 1. Ajout d'une règle
    rule_id = temp_db.add_learning(
        rule_text="Quand Alexis dit 'Troyes' en contexte RPE, interpréter le chiffre 3",
        category="phonetic",
        original_error="Troyes",
        correction="3",
        active=True,
    )
    assert isinstance(rule_id, int)
    assert rule_id > 0

    # 2. Récupération des règles actives
    active_rules = temp_db.get_active_learnings()
    assert len(active_rules) == 1
    assert active_rules[0]["id"] == rule_id
    assert active_rules[0]["original_error"] == "Troyes"
    assert active_rules[0]["correction"] == "3"
    assert active_rules[0]["category"] == "phonetic"

    # 3. Désactivation de la règle
    updated = temp_db.update_learning(rule_id, active=False)
    assert updated is True
    assert len(temp_db.get_active_learnings()) == 0

    # 4. Réactivation
    temp_db.update_learning(rule_id, active=True)
    assert len(temp_db.get_active_learnings()) == 1

    # 5. Suppression
    deleted = temp_db.delete_learning(rule_id)
    assert deleted is True
    assert len(temp_db.get_active_learnings()) == 0


def test_intent_parser_detects_teach_assistant():
    """Vérifie la détection locale des ordres d'apprentissage et de correction vocale."""
    parser = IntentParser()

    # Formule avec 'tu as compris X alors que j'ai dit Y'
    p1 = parser.parse("Attention là tu as compris Troyes alors que je t'ai dit 3")
    assert p1.intent == IntentType.TEACH_ASSISTANT
    assert p1.parameters.get("original_error") == "Troyes"
    assert p1.parameters.get("correction") == "3"

    # Formule avec 'quand je dis X je veux dire Y'
    p2 = parser.parse("Quand je dis renfort je veux dire renforcement")
    assert p2.intent == IntentType.TEACH_ASSISTANT
    assert p2.parameters.get("original_error") == "renfort"
    assert p2.parameters.get("correction") == "renforcement"

    # Formule avec 'le quinoa va dans le rayon épicerie'
    p3 = parser.parse("Le quinoa va dans le rayon épicerie")
    assert p3.intent == IntentType.TEACH_ASSISTANT
    assert p3.parameters.get("category") == "rayon"


def test_interact_teach_assistant_saves_rule_and_retro_corrects(temp_db):
    """Vérifie le flux complet de correction d'Otis via /api/v1/interact."""
    # 1. Simuler un échange préalable ayant produit une confusion
    prev_log_id = temp_db.log_conversation(
        session_id="session-teach",
        raw_query="RPE à Troyes",
        intent="log_sport_session",
        parameters={"notes": "RPE à Troyes"},
        spoken_response="Séance enregistrée",
        success=True,
    )

    client = TestClient(app)

    # 2. Alexis corrige Otis
    correction_query = "Attention là tu as compris Troyes alors que je t'ai dit 3"
    resp = client.post(
        "/api/v1/interact",
        json={"query": correction_query, "session_id": "session-teach"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    spoken = data["spoken_response"].lower()
    assert "noté" in spoken or "retenu" in spoken or "compris" in spoken

    # 3. Vérifier qu'une règle a bien été insérée dans user_learnings
    learnings = temp_db.get_active_learnings()
    assert len(learnings) >= 1
    last_rule = learnings[0]
    assert "troyes" in last_rule["rule_text"].lower() or last_rule["original_error"] == "Troyes"

    # 4. Vérifier qu'un feedback a été enregistré sur le log précédent
    feedbacks = temp_db.get_feedbacks_for_log(prev_log_id)
    assert len(feedbacks) >= 1
    assert feedbacks[0]["feedback_type"] == "correction"


def test_learnings_are_injected_dynamically_in_nlu_prompt(temp_db):
    """Vérifie que les règles de user_learnings sont automatiquement injectées dans le prompt NLU."""
    temp_db.add_learning(
        rule_text="Le quinoa va systématiquement dans le rayon Épicerie",
        category="rayon",
        original_error="quinoa",
        correction="Épicerie",
        active=True,
    )

    # Création du service NLU
    mock_client = MagicMock()
    mock_client.is_configured = True
    mock_client.is_daily_quota_exceeded.return_value = False
    mock_client.resolve_model = AsyncMock(return_value="gemini-3.5-flash-lite")
    mock_client.get_candidate_models.return_value = ["gemini-3.5-flash-lite"]

    nlu = GeminiNLUService(gemini_client=mock_client)

    # Construction du prompt
    prompt = nlu.build_system_prompt_with_learnings()
    assert "quinoa" in prompt.lower()
    assert "épicerie" in prompt.lower()
    assert "RÈGLES ET CORRECTIONS APPRISES" in prompt


def test_system_learnings_rest_endpoints(temp_db):
    """Vérifie les endpoints REST sous /api/v1/system/learnings."""
    client = TestClient(app)

    # 1. Création d'une règle via POST
    payload = {
        "rule_text": "Toujours allumer la prise salon le soir",
        "category": "habit",
        "original_error": None,
        "correction": None,
    }
    resp_create = client.post("/api/v1/system/learnings", json=payload)
    assert resp_create.status_code == 201
    created = resp_create.json()
    assert created["id"] > 0
    rule_id = created["id"]

    # 2. Consultation GET
    resp_list = client.get("/api/v1/system/learnings")
    assert resp_list.status_code == 200
    data_list = resp_list.json()
    assert data_list["total"] >= 1

    # 3. Désactivation PATCH
    resp_patch = client.patch(f"/api/v1/system/learnings/{rule_id}", json={"active": False})
    assert resp_patch.status_code == 200
    assert resp_patch.json()["active"] is False

    # 4. Suppression DELETE
    resp_del = client.delete(f"/api/v1/system/learnings/{rule_id}")
    assert resp_del.status_code == 200
    assert resp_del.json()["success"] is True
