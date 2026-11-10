"""Refonte UX (ROADMAP Étape 1, accueil) : « Dernières actions » — les 3 dernières modifications faites par Otis,
avec un libellé court, lues dans le journal des conversations (les simples lectures sont ignorées)."""
import pytest
from fastapi.testclient import TestClient

from app.core.home.recent_actions import action_label, recent_actions
from app.main import app


def _agent(*calls):
    return {"tool_calls": [{"name": n, "args": a, "error": e} for n, a, e in calls]}


def _log(intent, parameters=None, session_id="s1", success=True, log_id=1, created_at="2026-11-10 17:36:00"):
    return {
        "id": log_id, "session_id": session_id, "intent": intent, "parameters": parameters or {},
        "success": success, "spoken_response": "Réponse d'Otis.", "created_at": created_at,
    }


# ---------- Libellés ----------

@pytest.mark.parametrize("calls, label", [
    ([("add_shopping_items", {"articles": [{"nom": "Lardon"}]}, None)], "Lardon ajouté aux courses"),
    ([("add_shopping_items", {"articles": [{"nom": "Lardon"}, {"nom": "Fromage blanc"}]}, None)],
     "Lardon et Fromage blanc ajoutés aux courses"),
    ([("add_shopping_items", {"articles": [{"nom": n} for n in ("Pain", "Lait", "Oeufs", "Riz", "Thé")]}, None)],
     "Pain, Lait et 3 autres ajoutés aux courses"),
    ([("remove_shopping_items", {"noms": ["Lessive"]}, None)], "Lessive retiré des courses"),
    ([("check_shopping_items", {"noms": ["Pomme", "Poire"], "coche": True}, None)], "Pomme et Poire cochés dans les courses"),
    ([("check_shopping_items", {"noms": ["Pomme"], "coche": False}, None)], "Pomme décoché dans les courses"),
    ([("clear_bought_shopping_items", {}, None)], "Articles achetés retirés des courses"),
    ([("add_task", {"titre": "Acheter du Permixon"}, None)], "Tâche ajoutée : Acheter du Permixon"),
    ([("complete_task", {"task_id": "abc"}, None)], "Tâche terminée"),
    ([("save_note", {"category": "thought", "content": "…"}, None)], "Note ajoutée au Second cerveau"),
    ([("set_meal", {"date": "2026-11-10", "moment": "soir", "plat": "Soupe vermicelle"}, None)],
     "Repas prévu : Soupe vermicelle"),
    ([("log_sport_session", {"date": "2026-11-09", "type_seance": "Course", "distance_km": 7.01}, None)],
     "Séance du lundi enregistrée · 7,01 km"),
    ([("log_sport_session", {"date": "2026-11-09", "type_seance": "Course", "distance_km": 10.0}, None)],
     "Séance du lundi enregistrée · 10 km"),
    ([("plan_sport_session", {"date": "2026-11-12", "type_seance": "Fractionné"}, None)], "Séance du jeudi planifiée"),
    ([("update_sport_session", {"session_id": 16, "changes": {"ressenti_rpe": 8}}, None)], "Séance modifiée"),
    ([("plan_weekly_training", {}, None)], "Semaine d'entraînement planifiée"),
    ([("undo_last_action", {}, None)], "Dernière action annulée"),
    ([("save_note", {}, None), ("add_task", {"titre": "Réviser le vélo"}, None)],
     "Note ajoutée au Second cerveau · Tâche ajoutée : Réviser le vélo"),
])
def test_agent_tool_calls_become_a_short_label(calls, label):
    assert action_label(_log("agent", _agent(*calls))) == label


@pytest.mark.parametrize("parameters", [
    _agent(("get_shopping_list", {}, None), ("find_sport_sessions", {}, None)),
    _agent(("add_task", {"titre": "X"}, "Google Tasks indisponible")),  # outil en échec : rien n'a changé
    {},
])
def test_agent_turn_without_successful_change_is_not_an_action(parameters):
    assert action_label(_log("agent", parameters)) is None


@pytest.mark.parametrize("intent, parameters, label", [
    ("add_shopping_item", {"items": [{"item": "Banane"}]}, "Banane ajouté aux courses"),
    ("save_note", {"note_id": 3, "category": "thought"}, "Note ajoutée au Second cerveau"),
    ("log_sport_session", {"session": {"date": "2026-10-15", "distance_km": None}}, "Séance du jeudi enregistrée"),
    ("plan_sport_session", {"session": {"date": "2026-10-16"}}, "Séance du vendredi planifiée"),
    ("undo_last_action", {"undone_action": {"batch_id": 1}}, "Dernière action annulée"),
    ("teach_assistant", {}, "Correction mémorisée"),
])
def test_legacy_intents_that_change_data_become_a_short_label(intent, parameters, label):
    assert action_label(_log(intent, parameters)) == label


@pytest.mark.parametrize("intent", ["get_shopping_list", "get_meal_plan", "list_tasks", "small_talk", "unknown"])
def test_reads_and_small_talk_are_not_actions(intent):
    assert action_label(_log(intent)) is None


# ---------- Sélection ----------

def test_keeps_the_three_latest_successful_actions_and_only_the_latest_of_my_session_is_undoable():
    logs = [  # du plus récent au plus ancien, comme le journal
        _log("get_shopping_list", log_id=9),
        _log("save_note", log_id=8, created_at="2026-11-10 17:36:00"),
        _log("add_task", {"titre": "X"}, log_id=7, success=False),
        _log("add_shopping_item", {"items": [{"item": "Lardon"}]}, log_id=6),
        _log("undo_last_action", log_id=5),
        _log("save_note", log_id=4),
    ]

    items = recent_actions(logs, session_id="s1")

    assert [(i.id, i.undoable) for i in items] == [(8, True), (6, False), (5, False)]
    assert items[0].created_at == "2026-11-10T17:36:00Z"  # SQLite stocke en UTC


def test_latest_action_from_another_session_or_an_undo_cannot_be_undone_from_here():
    assert recent_actions([_log("save_note", session_id="autre")], session_id="s1")[0].undoable is False
    assert recent_actions([_log("undo_last_action")], session_id="s1")[0].undoable is False


# ---------- Route ----------

def test_route_reads_the_conversation_journal(isolate_sqlite_database):
    db = isolate_sqlite_database
    db.log_conversation("ajoute du lait", "add_shopping_item", "Ok", session_id="pwa_1",
                        parameters={"items": [{"item": "Lait"}]})
    db.log_conversation("donne-moi la liste", "get_shopping_list", "Voici…", session_id="pwa_1")

    res = TestClient(app).get("/api/v1/home/recent-actions", params={"session_id": "pwa_1"})

    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert [(i["label"], i["undoable"]) for i in items] == [("Lait ajouté aux courses", True)]


# ---------- Formats réels du journal de prod (500 du 10/11) ----------

def test_rayon_question_alone_is_not_an_action_and_string_items_are_not_added_articles():
    params = {"items": ["champignon"], "item": "champignon", "rayon_question": {"article": "Champignon"}}
    assert action_label(_log("add_shopping_item", params)) is None


def test_rayon_answer_that_adds_the_article_is_an_action():
    params = {"items": [{"item": "Champignon", "is_bought": False, "rayon": "Légumes"}]}
    assert action_label(_log("choose_rayon", params)) == "Champignon ajouté aux courses"
    assert action_label(_log("choose_rayon", {})) is None


def test_a_malformed_journal_entry_is_skipped_with_a_warning_instead_of_breaking_the_home(caplog):
    logs = [
        _log("log_sport_session", {"session": {"date": "2026-11-09", "distance_km": "sept"}}, log_id=2),
        _log("save_note", log_id=1),
    ]

    items = recent_actions(logs, session_id="s1")

    assert [i.id for i in items] == [1]
    assert "journal n°2" in caplog.text
