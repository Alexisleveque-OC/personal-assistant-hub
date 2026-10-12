"""Tests unitaires et d'intégration pour la mémoire conversationnelle multi-tours (Étape 6).

Vérifie l'éradication du mode stateless :
- Maintien continu de l'historique dans la session active
- Persistance et rechargement de session depuis SQLite (résilience après reboot / worker crash)
- Respect du TTL (Time-To-Live) pour éviter la pollution de sessions anciennes
- Résolution contextuelle des anaphores et références croisées (« C'est l'application », « Prends note de ces 3 derniers échanges »)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import DatabaseManager, set_database_manager
from app.core.models import IntentType, ParsedIntent
from app.core.dependencies import (
    clear_sessions,
    get_sessions_store,
    set_meals_connector,
    set_sport_connector,
)
from app.core.session_manager import get_session_manager, SessionManager

client = TestClient(app)
API_HEADERS = {"X-API-Key": "test_api_key"}


@pytest.fixture
def temp_db(tmp_path):
    """Initialise une base SQLite temporaire isolée pour les tests."""
    db_file = tmp_path / "test_session_memory.db"
    mgr = DatabaseManager(db_path=str(db_file))
    mgr.init_db()
    set_database_manager(mgr)
    clear_sessions()
    sess_mgr = get_session_manager()
    sess_mgr.clear_all()
    yield mgr
    clear_sessions()
    sess_mgr.clear_all()


def test_session_manager_tracks_turns_and_history(temp_db):
    """Vérifie que le SessionManager conserve et limite correctement l'historique des échanges."""
    sess_mgr = get_session_manager()
    session_id = "test-session-history-1"

    # Enregistrement d'un premier tour
    sess_mgr.record_turn(
        session_id=session_id,
        user_text="L'envoi des messages vocaux ne fonctionne pas",
        assistant_text="C'est un problème matériel ou c'est l'application ?",
    )

    ctx = sess_mgr.get_session(session_id)
    assert "history" in ctx
    assert len(ctx["history"]) == 2
    assert ctx["history"][0]["role"] == "user"
    assert ctx["history"][0]["text"] == "L'envoi des messages vocaux ne fonctionne pas"
    assert "timestamp" in ctx["history"][0]
    assert ctx["history"][1]["role"] == "assistant"
    assert ctx["history"][1]["text"] == "C'est un problème matériel ou c'est l'application ?"
    assert "timestamp" in ctx["history"][1]

    # Enregistrement d'un second tour
    sess_mgr.record_turn(
        session_id=session_id,
        user_text="C'est l'application",
        assistant_text="Compris, je note le problème sur l'application.",
    )

    ctx2 = sess_mgr.get_session(session_id)
    assert len(ctx2["history"]) == 4
    assert ctx2["history"][2]["text"] == "C'est l'application"


def test_session_window_preserves_up_to_20_turns(temp_db):
    """Vérifie que la fenêtre de session conserve jusqu'à 20 messages récents (10 allers-retours)."""
    sess_mgr = get_session_manager()
    session_id = "test-session-20-turns"

    # Enregistrer 12 allers-retours (24 messages au total)
    for i in range(1, 13):
        sess_mgr.record_turn(
            session_id=session_id,
            user_text=f"Question {i}",
            assistant_text=f"Réponse {i}",
        )

    ctx = sess_mgr.get_session(session_id)
    assert len(ctx["history"]) == 20
    # Le premier message conservé doit être Question 3 (puisque 1 et 2 ont glissé hors de la fenêtre)
    assert ctx["history"][0]["text"] == "Question 3"
    assert ctx["history"][-1]["text"] == "Réponse 12"


def test_session_reloads_from_sqlite_after_server_restart(temp_db):
    """Vérifie la résilience : après un crash/restart du serveur (RAM vidée),
    la session est restaurée depuis SQLite sans perte de mémoire conversationnelle."""
    sess_mgr = get_session_manager()
    session_id = "test-session-resilience-42"

    # Simulation d'un premier échange enregistré dans SQLite via temp_db.log_conversation
    temp_db.log_conversation(
        session_id=session_id,
        raw_query="L'envoi des messages vocaux ne fonctionne pas",
        intent="unknown",
        parameters={},
        spoken_response="C'est un problème matériel ou c'est l'application ?",
        success=True,
    )

    # Simulation d'un redémarrage complet du serveur / perte de RAM
    clear_sessions()
    sess_mgr.clear_all()

    # Le session manager doit recharger l'historique depuis SQLite
    ctx = sess_mgr.get_session(session_id)
    assert "history" in ctx
    assert len(ctx["history"]) >= 2
    assert ctx["history"][0]["role"] == "user"
    assert "L'envoi des messages vocaux ne fonctionne pas" in ctx["history"][0]["text"]
    assert ctx["history"][1]["role"] == "assistant"
    assert "C'est un problème matériel ou c'est l'application ?" in ctx["history"][1]["text"]


def test_session_expires_after_ttl_inactivity(temp_db):
    """Vérifie qu'une session ancienne (> TTL de 24h) est renouvelée pour éviter la confusion temporelle."""
    sess_mgr = get_session_manager()
    session_id = "test-session-expired-ttl"

    # Enregistrement d'un échange avec un timestamp datant de 25 heures
    old_time = datetime.now() - timedelta(hours=25)
    sess_mgr.record_turn(
        session_id=session_id,
        user_text="Message ancien d'hier",
        assistant_text="Réponse ancienne",
    )
    # Forcer l'âge de la session
    sess_mgr._sessions[session_id]["last_active"] = old_time

    # La session doit être expirée
    ctx = sess_mgr.get_session(session_id)
    assert ctx.get("history") == [] or "history" not in ctx


@pytest.mark.asyncio
async def test_interact_injects_full_history_into_llm(temp_db):
    """Vérifie que l'endpoint /api/v1/interact injecte systématiquement l'historique récent au LLM."""
    session_id = "session-full-history-llm"

    mock_nlu = AsyncMock()
    mock_nlu.parse.return_value = ParsedIntent(
        intent=IntentType.UNKNOWN,
        confidence=1.0,
        parameters={},
        raw_query="C'est l'application",
        conversational_reply="Entendu pour l'application.",
    )

    with patch("app.main.get_nlu_service", return_value=mock_nlu), \
         patch("app.routers.interact.get_nlu_service", return_value=mock_nlu):
        # Tour 1
        r1 = client.post(
            "/api/v1/interact",
            headers=API_HEADERS,
            json={
                "query": "L'envoi des messages vocaux ne fonctionne pas",
                "session_id": session_id,
            },
        )
        assert r1.status_code == 200

        # Tour 2
        r2 = client.post(
            "/api/v1/interact",
            headers=API_HEADERS,
            json={
                "query": "C'est l'application",
                "session_id": session_id,
            },
        )
        assert r2.status_code == 200

        # Vérifier que le NLU a bien reçu l'historique contenant le Tour 1
        mock_nlu.parse.assert_called()
        last_call_args = mock_nlu.parse.call_args
        context_passed = last_call_args.kwargs.get("context") or last_call_args.args[1]
        assert "history" in context_passed
        assert len(context_passed["history"]) >= 2
        assert any("L'envoi des messages vocaux" in h["text"] for h in context_passed["history"])


def test_note_capture_from_recent_exchanges_context(temp_db):
    """Vérifie la capture d'une note synthétisée quand l'utilisateur dit :
    'prends note de ces 3 derniers échanges. Il faut corriger'."""
    sess_mgr = get_session_manager()
    session_id = "session-note-anaphora"

    # Préparation de l'historique conversationnel
    sess_mgr.record_turn(
        session_id=session_id,
        user_text="L'envoi des messages vocaux ne fonctionne pas",
        assistant_text="C'est un problème matériel ou c'est l'application ?",
    )
    sess_mgr.record_turn(
        session_id=session_id,
        user_text="C'est l'application",
        assistant_text="D'accord, je note le problème sur l'application.",
    )

    r = client.post(
        "/api/v1/interact",
        headers=API_HEADERS,
        json={
            "query": "Prends note de ces derniers échanges. Il faut corriger",
            "session_id": session_id,
        },
    )
    assert r.status_code == 200
    res_data = r.json()
    assert res_data["intent"]["intent"] == IntentType.SAVE_NOTE.value
    assert res_data["data"]["category"] in ("bug_report", "dev_idea")

    # Vérifier que le contenu enregistré en base contient les éléments de la discussion
    notes = temp_db.get_notes(category=res_data["data"]["category"])
    assert notes["total"] >= 1
    last_note = notes["items"][0]
    assert "messages vocaux" in last_note["content"] or "application" in last_note["content"]


def test_interact_updates_sport_session_with_contextual_rpe(temp_db):
    """Vérifie que 'Il fallait en modifier le rpe a 3' utilise la séance active en mémoire."""
    from app.connectors.sqlite.sport_connector import SqlSportConnector
    sport_conn = SqlSportConnector(db_manager=temp_db)
    set_sport_connector(sport_conn)

    sess_mgr = get_session_manager()
    session_id = "session-sport-context-rpe"
    target_date = "2026-10-11"
    temp_db.add_sport_session({
        "date": target_date,
        "type_seance": "Renforcement",
        "statut": "Réalisé",
        "duration_seconds": 1800,
        "ressenti_rpe": 5,
        "notes": "Mobilité et renfo",
    })

    # Tour 1 : consultation de la dernière séance
    r1 = client.post(
        "/api/v1/interact",
        headers=API_HEADERS,
        json={
            "query": "C'était quoi ma dernière séance ?",
            "session_id": session_id,
        },
    )
    assert r1.status_code == 200
    assert "Renforcement" in r1.json()["spoken_response"]

    # Tour 2 : "Il fallait en modifier le rpe a 3" (anaphore sans date explicite)
    r2 = client.post(
        "/api/v1/interact",
        headers=API_HEADERS,
        json={
            "query": "Il fallait en modifier le rpe a 3",
            "session_id": session_id,
        },
    )
    assert r2.status_code == 200
    res2 = r2.json()
    assert res2["intent"]["intent"] == IntentType.UPDATE_SPORT_SESSION.value
    assert res2["data"].get("ressenti_rpe") == 3
    # Vérification en base SQLite
    saved_sess = temp_db.get_sport_session_by_date(target_date)
    assert saved_sess["ressenti_rpe"] == 3

