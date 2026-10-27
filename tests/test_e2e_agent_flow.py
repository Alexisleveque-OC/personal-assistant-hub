"""E2E Phase 6.8 (Étape 6) : une conversation complète en mode agent, de la phrase à la réponse.

Phrase → /interact → agent (LLM scripté, seul élément simulé) → vrais outils → SQLite et classeur en mémoire → réponse.
Couvre sport, courses avec rayon inconnu (question puis réponse traitée sans LLM), note sur l'échange précédent et
annulation déterministe. L'appel réel à Gemini est validé à part par le golden set (`RUN_LIVE_GEMINI=1`).
"""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.connectors.sheets.meals_connector import MealsShoppingConnector
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.factory import set_agent_llm
from app.core.clock import paris_today
from app.core.dependencies import set_meals_connector, set_sport_connector
from app.core.session_manager import get_session_manager
from app.main import app
from tests.agent_fakes import ScriptedLLM, call_turn, text_turn
from tests.meals_fakes import MealsSheetState, build_meals_spreadsheet, waiting_rows

SESSION = "e2e-agent"


@pytest.fixture
def env(isolate_sqlite_database, monkeypatch):
    monkeypatch.setattr(settings, "nlu_mode", "agent")
    set_sport_connector(SqlSportConnector(db_manager=isolate_sqlite_database))
    sheet = build_meals_spreadsheet(MealsSheetState(today=paris_today(), waiting=[("Pain", False)]))
    set_meals_connector(MealsShoppingConnector(spreadsheet=sheet))
    yield isolate_sqlite_database, sheet
    get_session_manager().clear_all()
    set_sport_connector(None)
    set_meals_connector(None)
    set_agent_llm(None)


def _ask(query: str) -> dict:
    resp = TestClient(app).post("/api/v1/interact", json={"query": query, "session_id": SESSION})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _rpe(db, session_id: int):
    with db.get_connection() as conn:
        return conn.execute("SELECT ressenti_rpe FROM sport_sessions WHERE id = ?", (session_id,)).fetchone()[0]


def _notes(db) -> list:
    with db.get_connection() as conn:
        return [row[0] for row in conn.execute("SELECT content FROM second_brain_notes ORDER BY id").fetchall()]


def test_full_agent_conversation_from_phrase_to_storage(env):
    db, sheet = env
    renfo = db.add_sport_session({
        "date": (paris_today() - timedelta(days=1)).isoformat(), "type_seance": "Renforcement", "statut": "Réalisé",
        "duree_secondes": 2400, "ressenti_rpe": 5,
    })
    llm = ScriptedLLM([
        # Tour 1 : sport, séance ciblée par son identifiant.
        # Modification simple : réponse rédigée par l'application, sans 2e appel Gemini.
        call_turn({"name": "update_sport_session", "args": {"session_id": renfo, "changes": {"ressenti_rpe": 3}}}),
        # Tour 2 : courses, un article connu et un inconnu (le modèle ne choisit pas le rayon) ; « et » = demande
        # composée, Gemini rédige la réponse.
        call_turn({"name": "add_shopping_items", "args": {"articles": [{"nom": "lait"}, {"nom": "bougies"}]}}),
        text_turn("J'ai ajouté le lait."),
        # Tour 3 (« En entretien ») : traité par le code, aucun tour LLM consommé.
        # Tour 4 : note sur l'échange précédent.
        call_turn({"name": "save_note", "args": {
            "content": "Bougies rangées en Entretien, à vérifier.", "category": "thought", "inclure_dernier_echange": True,
        }}),
    ])
    set_agent_llm(llm)

    sport = _ask("Passe le RPE de ma renfo d'hier à 3")
    assert sport["success"] is True and sport["spoken_response"].startswith("C'est noté : RPE 3 pour ta renfo du ")
    assert _rpe(db, renfo) == 3

    shopping = _ask("Ajoute du lait et des bougies à la liste de courses de la semaine")
    assert shopping["spoken_response"].startswith("J'ai ajouté le lait. Je ne connais pas encore le rayon de « Bougies »")
    assert waiting_rows(sheet)[-1] == ("Lait", False)

    rayon = _ask("En entretien")
    assert rayon["intent"]["intent"] == "choose_rayon"
    assert waiting_rows(sheet)[-1] == ("Bougies", False)
    assert sheet.worksheet("Ingredients_Rayons").get_all_values()[-1] == ["Bougies", "Entretien"]

    note = _ask("Note ces derniers échanges")
    assert note["spoken_response"] == "C'est noté dans tes réflexions."
    assert _notes(db)[-1].endswith(f"Toi : En entretien\nOtis : {rayon['spoken_response']}")

    undo = _ask("annule ça")
    assert undo["success"] is True
    assert _notes(db) == []
    # Sport et note : 1 appel ; courses (demande composée) : 2 ; réponse au rayon et annulation : aucun.
    assert len(llm.requests) == 4
    assert note["data"]["note_id"] is not None
