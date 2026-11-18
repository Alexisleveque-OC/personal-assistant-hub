"""« Annuler » sur les 3 dernières actions (ROADMAP) : chaque action annulable est liée à son lot d'annulation."""
import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.connectors.sheets.meals_connector import MealsShoppingConnector
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.factory import set_agent_llm
from app.core.agent.undo import UndoError
from app.core.clock import paris_today
from app.core.dependencies import set_meals_connector, set_sport_connector
from app.core.session_manager import get_session_manager
from app.main import app
from tests.agent_fakes import ScriptedLLM, call_turn, text_turn
from tests.meals_fakes import MealsSheetState, build_meals_spreadsheet, waiting_rows

SESSION = "phone-1"


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


def _ask(query: str, session_id: str = SESSION) -> dict:
    resp = TestClient(app).post("/api/v1/interact", json={"query": query, "session_id": session_id})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _logged_batch_id(db, log_id: int):
    with db.get_connection() as conn:
        raw = conn.execute("SELECT parameters FROM conversation_logs WHERE id = ?", (log_id,)).fetchone()[0]
    return json.loads(raw).get("undo_batch_id")


def _last_batch_id(db, session_id: str = SESSION) -> int:
    return db.get_last_agent_undo_batch(session_id)["id"]


def test_agent_action_is_logged_with_its_undo_batch(env):
    db, _ = env
    set_agent_llm(ScriptedLLM([
        call_turn({"name": "save_note", "args": {"content": "Penser aux piles", "category": "thought"}}),
        text_turn("C'est noté."),
    ]))

    reply = _ask("Note que je dois penser aux piles")

    assert reply["data"]["undo_batch_id"] == _last_batch_id(db)
    assert _logged_batch_id(db, reply["data"]["log_id"]) == _last_batch_id(db)


def test_read_only_agent_turn_has_no_undo_batch(env):
    db, _ = env
    set_agent_llm(ScriptedLLM([call_turn({"name": "find_sport_sessions", "args": {}}), text_turn("Aucune séance.")]))

    reply = _ask("Quelles sont mes dernières séances ?")

    assert "undo_batch_id" not in reply["data"]
    assert _logged_batch_id(db, reply["data"]["log_id"]) is None


def test_fast_lane_shopping_addition_records_an_undo_batch(env):
    db, _ = env
    set_agent_llm(ScriptedLLM([]))  # voie rapide : aucun appel au LLM

    reply = _ask("ajoute du lait")

    batch = db.get_last_agent_undo_batch(SESSION)
    assert batch is not None and json.loads(batch["undos_json"]) == [{"kind": "shopping_added", "items": ["Lait"]}]
    assert _logged_batch_id(db, reply["data"]["log_id"]) == batch["id"]


# --- Étape 3 : annuler un lot précis ---------------------------------------------------------------------------------

def _undo(batch_id: int, session_id: str = SESSION):
    from app.core.agent.factory import build_undo_service
    from app.core.dependencies import get_meals_connector, get_sport_connector

    return build_undo_service(get_sport_connector(), get_meals_connector()).undo_batch(session_id, batch_id)


def _waiting(sheet) -> list:
    return [name for name, _ in waiting_rows(sheet)]


def test_an_older_action_is_undone_while_the_newer_one_is_kept(env):
    db, sheet = env
    set_agent_llm(ScriptedLLM([
        call_turn({"name": "save_note", "args": {"content": "Penser aux piles", "category": "thought"}}),
        text_turn("C'est noté."),
    ]))
    note = _ask("Note que je dois penser aux piles")
    _ask("ajoute du lait")

    outcome = _undo(note["data"]["undo_batch_id"])

    assert outcome.restored == ["note « Penser aux piles » supprimée"]
    assert db.get_notes(limit=5)["items"] == []
    assert _waiting(sheet) == ["Pain", "Lait"]  # l'action plus récente est conservée


def test_undo_is_refused_when_a_newer_action_changed_the_same_data(env):
    _, sheet = env
    added = _ask("ajoute du lait")
    set_agent_llm(ScriptedLLM([call_turn({"name": "check_shopping_items", "args": {"noms": ["lait"]}}), text_turn("Coché.")]))
    _ask("j'ai pris le lait")

    with pytest.raises(UndoError):
        _undo(added["data"]["undo_batch_id"])

    assert waiting_rows(sheet)[-1] == ("Lait", True)  # rien n'a été restauré


def test_undo_is_refused_for_another_device_an_unknown_batch_or_twice(env):
    added = _ask("ajoute du lait")
    batch_id = added["data"]["undo_batch_id"]

    with pytest.raises(UndoError, match="autre appareil"):
        _undo(batch_id, session_id="phone-2")
    with pytest.raises(UndoError, match="introuvable"):
        _undo(batch_id + 100)
    _undo(batch_id)
    with pytest.raises(UndoError, match="déjà annulée"):
        _undo(batch_id)


# --- Étape 4 : API ---------------------------------------------------------------------------------------------------

def _undo_route(log_id: int, session_id: str = SESSION):
    return TestClient(app).post(f"/api/v1/home/recent-actions/{log_id}/undo", params={"session_id": session_id})


def _recent(session_id: str = SESSION) -> list:
    res = TestClient(app).get("/api/v1/home/recent-actions", params={"session_id": session_id})
    assert res.status_code == 200, res.text
    return [(i["label"], i["undoable"], i["undone"]) for i in res.json()["items"]]


def test_route_undoes_an_older_action_and_the_list_shows_it_undone(env):
    db, sheet = env
    set_agent_llm(ScriptedLLM([
        call_turn({"name": "save_note", "args": {"content": "Penser aux piles", "category": "thought"}}),
        text_turn("C'est noté."),
    ]))
    note = _ask("Note que je dois penser aux piles")
    _ask("ajoute du lait")

    res = _undo_route(note["data"]["log_id"])

    assert res.status_code == 200, res.text
    assert res.json()["spoken_response"] == "C'est annulé : note « Penser aux piles » supprimée."
    assert db.get_notes(limit=5)["items"] == []
    assert _recent() == [("Lait ajouté aux courses", True, False), ("Note ajoutée au Second cerveau", False, True)]
    journal = db.get_conversation_logs(limit=1)["items"][0]
    assert journal["intent"] == "undo_recent_action" and journal["session_id"] == SESSION


def test_route_explains_why_an_action_cannot_be_undone(env):
    _, sheet = env
    added = _ask("ajoute du lait")
    set_agent_llm(ScriptedLLM([call_turn({"name": "check_shopping_items", "args": {"noms": ["lait"]}}), text_turn("Coché.")]))
    _ask("j'ai pris le lait")

    conflict = _undo_route(added["data"]["log_id"])
    other_device = _undo_route(added["data"]["log_id"], session_id="phone-2")

    assert conflict.status_code == 409 and conflict.json()["detail"] == "Annulation impossible : Lait a été coché depuis."
    assert other_device.status_code == 409 and "autre appareil" in other_device.json()["detail"]
    assert waiting_rows(sheet)[-1] == ("Lait", True)


def test_route_refuses_an_action_without_undo_batch_or_an_unknown_one(env, isolate_sqlite_database):
    log_id = isolate_sqlite_database.log_conversation("retiens ça", "teach_assistant", "Ok", session_id=SESSION)

    no_batch = _undo_route(log_id)
    unknown = _undo_route(log_id + 100)

    assert no_batch.status_code == 409 and "ne peut pas être annulée" in no_batch.json()["detail"]
    assert unknown.status_code == 404
