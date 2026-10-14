"""Test d'intégration End-to-End (E2E) complet pour la feature :
Audio Focus Casque, Pipeline Vocal & Stabilisation Avancée (Étape 5).

Valide le flux complet utilisateur de bout en bout :
1. Enregistrement d'une séance sportive par commande vocale/texte.
2. Débriefing et transition vers une prise de note contextuelle sans collision sportive.
3. Prise de note orale naturelle sans ponctuation sans collision avec la liste de courses.
4. Ajout d'article de courses contenant du vocabulaire de running sans fausse mutation sport.
5. Intégrité des assets PWA (Audio Focus, Offline Outbox, Service Worker v20).
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import get_database_manager
from app.core.models import IntentType, NoteCategory

client = TestClient(app)


def test_e2e_complete_voice_and_resilience_pipeline():
    """Test de cycle de vie complet de l'assistant de bout en bout."""
    session_id = "test_e2e_full_lifecycle_session"
    db = get_database_manager()

    # -------------------------------------------------------------------------
    # 1. Enregistrement d'une séance sportive (Sport Flow)
    # -------------------------------------------------------------------------
    res_sport = client.post(
        "/api/v1/interact",
        json={
            "query": "J'ai couru 10km en 50 minutes ce matin",
            "session_id": session_id,
        },
    )
    assert res_sport.status_code == 200, f"Erreur sport: {res_sport.text}"
    data_sport = res_sport.json()
    assert data_sport["success"] is True
    assert data_sport["intent"]["intent"] == IntentType.LOG_SPORT_SESSION.value
    assert "10" in data_sport["spoken_response"] or "séance" in data_sport["spoken_response"].lower()

    # -------------------------------------------------------------------------
    # 2. Prise de note contextuelle multi-tours sur l'échange (Second Cerveau)
    # Ne doit JAMAIS muter la séance précédente (RPE 3/10 ou 3 séances).
    # -------------------------------------------------------------------------
    res_context_note = client.post(
        "/api/v1/interact",
        json={
            "query": "Ok prends note de ces 3 derniers échanges. Il faut corriger la cadence",
            "session_id": session_id,
        },
    )
    assert res_context_note.status_code == 200
    data_context_note = res_context_note.json()
    assert data_context_note["intent"]["intent"] == IntentType.SAVE_NOTE.value
    assert data_context_note["intent"]["intent"] != IntentType.UPDATE_SPORT_SESSION.value
    assert "noté" in data_context_note["spoken_response"].lower() or "note" in data_context_note["spoken_response"].lower()

    # -------------------------------------------------------------------------
    # 3. Prise de note orale naturelle sans ponctuation (Cas exact d'Alexis)
    # Ne doit JAMAIS être ajoutée à la liste de courses.
    # -------------------------------------------------------------------------
    res_oral_note = client.post(
        "/api/v1/interact",
        json={
            "query": "Ajoute une note juste pour penser à vérifier la connexion.",
            "session_id": session_id,
        },
    )
    assert res_oral_note.status_code == 200
    data_oral_note = res_oral_note.json()
    assert data_oral_note["intent"]["intent"] == IntentType.SAVE_NOTE.value
    assert data_oral_note["intent"]["intent"] != IntentType.ADD_SHOPPING_ITEM.value
    assert "courses" not in data_oral_note["spoken_response"].lower()

    # Vérification en base SQLite que la note a bien été enregistrée
    notes_res = db.get_notes(limit=5)
    notes = notes_res["items"]
    matching_notes = [n for n in notes if "vérifier la connexion" in n["content"].lower()]
    assert len(matching_notes) > 0, "La note n'a pas été persistée dans le Second Cerveau"

    # -------------------------------------------------------------------------
    # 4. Ajout d'un article de courses contenant du vocabulaire running
    # Doit aller sur la liste de courses et ne pas altérer le sport.
    # -------------------------------------------------------------------------
    res_shop = client.post(
        "/api/v1/interact",
        json={
            "query": "Ajoute des barres énergétiques pour mon footing à la liste de courses",
            "session_id": session_id,
        },
    )
    assert res_shop.status_code == 200
    data_shop = res_shop.json()
    assert data_shop["intent"]["intent"] == IntentType.ADD_SHOPPING_ITEM.value
    assert data_shop["intent"]["intent"] != IntentType.LOG_SPORT_SESSION.value
    assert data_shop["intent"]["intent"] != IntentType.UPDATE_SPORT_SESSION.value

    # -------------------------------------------------------------------------
    # 5. Cohérence des composants PWA & Offline Outbox
    # -------------------------------------------------------------------------
    res_sw = client.get("/sw.js")
    assert res_sw.status_code == 200
    assert "pah-pwa-cache-v20" in res_sw.text
    assert "/static/js/offline_outbox.js" in res_sw.text
    assert "status: 503" in res_sw.text

    res_outbox = client.get("/static/js/offline_outbox.js")
    assert res_outbox.status_code == 200
    assert "syncOutbox" in res_outbox.text
    assert "startAutoRetry" in res_outbox.text

    res_audio_focus = client.get("/static/js/audio_focus.js")
    assert res_audio_focus.status_code == 200
    assert "audioFocusManager" in res_audio_focus.text
