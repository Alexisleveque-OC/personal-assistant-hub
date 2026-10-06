"""Tests unitaires (TDD) pour l'explication pédagogique d'exercices de renforcement et la vulgarisation des termes kiné."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.core.models import IntentType
from app.core.intent_parser import IntentParser
from app.core.sport_coach_service import SportCoachService, EXERCISE_GUIDE, SPORT_COACH_SYSTEM_PROMPT
from app.main import app


def test_intent_type_contains_explain_sport_exercise():
    """Vérifie la présence de l'intention EXPLAIN_SPORT_EXERCISE."""
    assert hasattr(IntentType, "EXPLAIN_SPORT_EXERCISE")
    assert IntentType.EXPLAIN_SPORT_EXERCISE == "explain_sport_exercise"


def test_local_parser_detects_explain_exercise_queries():
    """Vérifie que le parser local déterministe détecte les demandes d'explication d'exercices sans jargon."""
    parser = IntentParser()

    queries = [
        ("comment je fais l'exercice de mollets sur une marche ?", "mollets sur une marche"),
        ("explique-moi l'exercice pour le mollet bas", "mollet bas"),
        ("comment faire le pont fessier sur une jambe ?", "pont fessier sur une jambe"),
        ("comment s'étirer les mollets contre un mur ?", "mollets contre un mur"),
        ("comment faire le gainage ?", "gainage"),
        ("explique-moi le renfo de mardi", "renfo"),
    ]

    for q, expected_snippet in queries:
        parsed = parser.parse(q)
        assert parsed.intent == IntentType.EXPLAIN_SPORT_EXERCISE, f"Échec pour la requête : {q}"
        assert "exercise" in parsed.parameters
        assert any(word in parsed.parameters["exercise"].lower() for word in expected_snippet.lower().split()[:2])


def test_exercise_guide_contains_clear_vulgarized_instructions():
    """Vérifie que le guide d'exercices contient des explications concrètes (installation, tempo, erreurs)."""
    assert len(EXERCISE_GUIDE) >= 4

    # Exemple de l'exercice phare pour la périostite : descente de mollets sur une marche
    cle = next((k for k in EXERCISE_GUIDE if "marche" in k or "mollet" in k), None)
    assert cle is not None
    info = EXERCISE_GUIDE[cle]
    assert "nom" in info
    assert "objectif" in info
    assert "installation" in info
    assert "mouvement" in info
    assert "tempo" in info
    assert "erreurs_a_eviter" in info


def test_coach_service_explain_exercise_returns_pedagogic_explanation():
    """Vérifie que la méthode explain_exercise retourne un texte clair, instructif et sans jargon médical."""
    mock_connector = MagicMock()
    coach = SportCoachService(connector=mock_connector)

    explanation = coach.explain_exercise("mollets sur une marche")
    assert explanation is not None
    assert "marche" in explanation.lower() or "mollet" in explanation.lower()
    # Aucun terme abscons non vulgarisé
    assert "gastrocnémien" not in explanation.lower()
    assert "soléaire" not in explanation.lower() or "mollet bas" in explanation.lower()


def test_prompt_forbids_medical_jargon_and_uses_vulgarized_terms():
    """Vérifie que le prompt coach proscrit formellement le jargon kiné incompréhensible."""
    prompt = SPORT_COACH_SYSTEM_PROMPT.lower()
    # On interdit d'imposer des termes bruts sans vulgarisation
    assert "jargon" in prompt or "vulgaris" in prompt or "mollet bas" in prompt or "jambe tendue" in prompt


def test_api_interact_handles_explain_sport_exercise(monkeypatch):
    """Vérifie que l'endpoint interact gère correctement l'explication d'un exercice."""
    client = TestClient(app)

    response = client.post(
        "/api/v1/interact",
        json={"query": "Comment je fais l'exercice de descente de mollets sur une marche ?"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["intent"]["intent"] == "explain_sport_exercise"
    assert "marche" in data["spoken_response"].lower() or "mollet" in data["spoken_response"].lower()
