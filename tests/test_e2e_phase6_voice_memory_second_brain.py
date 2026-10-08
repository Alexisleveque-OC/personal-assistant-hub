"""Test d'intégration End-to-End (E2E) pour la Phase 6 :

Moteur Vocal Haute-Fidélité, Mémoire Long-terme & Second Cerveau.

Valide le flux complet :
1. Normalisation phonétique & audio direct
2. Auto-apprentissage interactif (teach_assistant) & feedback
3. Second Cerveau compartimenté (dictée texte & screenshot via Gemini Vision)
4. Commande d'annulation immédiate (Undo contextuel)
5. Audit conversationnel et consultation REST
"""
import io
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import get_database_manager
from app.core.models import (
    IntentType,
    ParsedIntent,
    SecondBrainImageAnalysisResult,
)


@pytest.fixture
def clean_db():
    """Initialise une base propre avant le test E2E."""
    db = get_database_manager()
    db.init_db()
    with db.get_connection() as conn:
        conn.execute("DELETE FROM conversation_feedbacks;")
        conn.execute("DELETE FROM user_learnings;")
        conn.execute("DELETE FROM second_brain_notes;")
        conn.execute("DELETE FROM conversation_logs;")
    return db


def test_e2e_phase6_full_user_journey(clean_db):
    """Parcours complet E2E Phase 6 : Vocal -> Apprentissage -> Second Cerveau -> Undo -> Audit."""
    client = TestClient(app)
    db = clean_db

    # =========================================================================
    # 1. Pipeline Audio Direct & Normalisation Phonétique
    # =========================================================================
    fake_audio = io.BytesIO(b"RIFF....WAVEfmt ....fakeaudiochunk....")

    parsed_audio_intent = ParsedIntent(
        raw_query="Qu'est-ce qu'on a sur la liste de courses ?",
        intent=IntentType.GET_SHOPPING_LIST,
        confidence=0.98,
        parameters={},
        conversational_reply="Voici vos articles de courses.",
    )

    with patch("app.core.audio.stt_service.AudioSTTService.process_audio") as mock_stt:
        # Simule transcription avec normalisation phonétique ("RPE à Troyes" -> "RPE à 3")
        mock_stt.return_value = ("Qu'est-ce qu'on a sur la liste de courses ?", parsed_audio_intent)

        res_audio = client.post(
            "/api/v1/interact/audio",
            files={"audio_file": ("test.webm", fake_audio, "audio/webm")},
            data={"session_id": "e2e_session_42"},
        )
        assert res_audio.status_code == 200
        data_audio = res_audio.json()
        assert data_audio["success"] is True
        assert "courses" in data_audio["transcribed_text"].lower()

    # Vérification que l'interaction audio est loguée dans conversation_logs
    logs = db.get_conversation_logs(session_id="e2e_session_42", limit=5)
    assert logs["total"] >= 1
    assert logs["items"][0]["intent"] == IntentType.GET_SHOPPING_LIST.value

    # =========================================================================
    # 2. Auto-Apprentissage Vocal Interactif (teach_assistant)
    # =========================================================================
    # Alexis corrige un malentendu oral
    teach_query = "Attention là tu as compris Troyes alors que je t'ai dit 3"

    res_teach = client.post(
        "/api/v1/interact",
        json={"query": teach_query, "session_id": "e2e_session_42"},
    )
    assert res_teach.status_code == 200
    data_teach = res_teach.json()
    assert data_teach["intent"]["intent"] == IntentType.TEACH_ASSISTANT.value
    assert "retenu" in data_teach["spoken_response"].lower() or "noté" in data_teach["spoken_response"].lower()

    # Vérification que la règle est stockée dans user_learnings
    learnings = db.get_learnings(active=True)
    assert learnings["total"] >= 1
    last_rule = learnings["items"][0]
    assert "3" in last_rule["rule_text"] or "troyes" in last_rule["rule_text"].lower()

    # =========================================================================
    # 3. Second Cerveau - Dictée de Notes (Texte & Image Vision)
    # =========================================================================
    # 3a. Dictée texte d'une idée dev
    res_note_dev = client.post(
        "/api/v1/interact",
        json={"query": "À dev : créer un widget météo pour la chronique", "session_id": "e2e_session_42"},
    )
    assert res_note_dev.status_code == 200
    assert res_note_dev.json()["intent"]["intent"] == IntentType.SAVE_NOTE.value

    # 3b. Dictée texte d'une note dynamique "voyage"
    res_note_voyage = client.post(
        "/api/v1/interact",
        json={"query": "Note voyage : louer un van en Islande pour l'été", "session_id": "e2e_session_42"},
    )
    assert res_note_voyage.status_code == 200

    # 3c. Envoi d'une capture d'écran de bug via Gemini Vision
    fake_screenshot = io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRfakeimage")
    mock_bug_analysis = SecondBrainImageAnalysisResult(
        category="bug_report",
        title="NullPointer sur le composant profil",
        summary="Capture d'un écran de crash avec message d'erreur et stacktrace.",
        tags=["bug", "crash", "ui"],
        suggested_action="Vérifier la nullité de l'objet utilisateur.",
    )

    with patch("app.routers.second_brain.analyze_image_for_second_brain") as mock_vision:
        mock_vision.return_value = mock_bug_analysis

        res_img = client.post(
            "/api/v1/second-brain/notes/image",
            files={"image": ("bug.png", fake_screenshot, "image/png")},
            data={"caption": "Crash constaté lors de la connexion"},
        )
        assert res_img.status_code == 201
        data_img = res_img.json()
        assert data_img["note"]["category"] == "bug_report"
        assert "NullPointer" in data_img["note"]["content"]

    # Consultation des statistiques dynamiques du Second Cerveau
    res_stats = client.get("/api/v1/second-brain/stats")
    assert res_stats.status_code == 200
    stats = res_stats.json()
    assert "dev_idea" in stats
    assert "bug_report" in stats

    # =========================================================================
    # 4. Commande d'Annulation Immédiate (« Undo »)
    # =========================================================================
    # Alexis ajoute une note erronée par erreur
    res_fake_note = client.post(
        "/api/v1/interact",
        json={"query": "Note que j'achète un sous-marin jaune", "session_id": "e2e_session_42"},
    )
    assert res_fake_note.status_code == 200
    created_note_id = res_fake_note.json()["data"]["note_id"]
    assert db.get_note(created_note_id) is not None

    # Alexis demande immédiatement l'annulation
    res_undo = client.post(
        "/api/v1/interact",
        json={"query": "Oups annule ma dernière commande", "session_id": "e2e_session_42"},
    )
    assert res_undo.status_code == 200
    data_undo = res_undo.json()
    assert data_undo["intent"]["intent"] == IntentType.UNDO_LAST_ACTION.value
    assert "annulé" in data_undo["spoken_response"].lower()

    # Vérification que la note erronée a été supprimée de la base de données
    assert db.get_note(created_note_id) is None

    # =========================================================================
    # 5. Audit Conversationnel & Consultation REST
    # =========================================================================
    res_audit = client.get("/api/v1/system/conversation-logs?limit=20")
    assert res_audit.status_code == 200
    audit_data = res_audit.json()
    assert audit_data["total"] >= 4

    # Dépôt d'un feedback utilisateur sur le premier log
    first_log_id = audit_data["items"][-1]["id"]
    res_fb = client.post(
        f"/api/v1/system/conversation-logs/{first_log_id}/feedback",
        json={"feedback_type": "positive", "user_note": "Excellente réponse rapide !"},
    )
    assert res_fb.status_code == 201
    assert res_fb.json()["success"] is True

    # Vérification que les notes restantes sont bien consultables et filtrables
    res_notes = client.get("/api/v1/second-brain/notes?category=bug_report")
    assert res_notes.status_code == 200
    bug_notes = res_notes.json()
    assert bug_notes["total"] >= 1
    assert any("NullPointer" in n["content"] for n in bug_notes["items"])
