"""Tests du branchement de l'agent dans /interact derrière l'interrupteur NLU_MODE (Phase 6.8 - Étape 3)."""
from datetime import date, timedelta
import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.errors import AgentUnavailableError
from app.core.agent.factory import set_agent_llm
from app.core.dependencies import set_sport_connector
from app.core.session_manager import get_session_manager
from app.main import app
from tests.agent_fakes import ScriptedLLM, call_turn, text_turn

TODAY = date.today().isoformat()


@pytest.fixture
def db(isolate_sqlite_database):
    set_sport_connector(SqlSportConnector(db_manager=isolate_sqlite_database))
    yield isolate_sqlite_database
    set_sport_connector(None)
    set_agent_llm(None)


@pytest.fixture
def agent_mode(monkeypatch):
    monkeypatch.setattr(settings, "nlu_mode", "agent")


def _ask(query: str, session_id: str = "agent-test") -> dict:
    resp = TestClient(app).post("/api/v1/interact", json={"query": query, "session_id": session_id})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _last_log(db) -> dict:
    with db.get_connection() as conn:
        return dict(conn.execute("SELECT * FROM conversation_logs ORDER BY id DESC LIMIT 1").fetchone())


def test_default_mode_is_legacy():
    from app.config import Settings
    assert Settings(_env_file=None).nlu_mode == "legacy"


def test_sport_request_goes_through_agent(db, agent_mode):
    session_id = db.add_sport_session({"date": TODAY, "type_seance": "EF", "statut": "Réalisé"})
    llm = ScriptedLLM([
        call_turn({"name": "update_sport_session", "args": {"session_id": session_id, "changes": {"ressenti_rpe": 5}}}),
    ])  # modification simple : réponse rédigée par l'application, pas de 2e appel Gemini (Étape 7)
    set_agent_llm(llm)

    body = _ask("Mets le RPE de ma séance du jour à 5")

    assert body["success"] is True
    assert body["spoken_response"].startswith("C'est noté : RPE 5 pour ton footing du ")
    assert body["intent"]["intent"] == "agent"
    assert body["data"]["session"]["id"] == session_id
    assert body["data"]["tool_calls"][0]["name"] == "update_sport_session"
    assert db.get_sport_session_by_id(session_id)["ressenti_rpe"] == 5

    log = _last_log(db)
    assert (log["intent"], log["success"]) == ("agent", 1)
    assert json.loads(log["parameters"])["tool_calls"][0]["name"] == "update_sport_session"

    history = get_session_manager().get_session("agent-test")["history"]
    assert [h["role"] for h in history[-2:]] == ["user", "assistant"]


def test_agent_turn_latency_details_are_logged(db, agent_mode):
    session_id = db.add_sport_session({"date": TODAY, "type_seance": "EF", "statut": "Réalisé"})
    set_agent_llm(ScriptedLLM([
        call_turn({"name": "update_sport_session", "args": {"session_id": session_id, "changes": {"ressenti_rpe": 5}}}),
    ]))

    _ask("Mets le RPE de ma séance du jour à 5")

    log = _last_log(db)
    parameters = json.loads(log["parameters"])
    assert parameters["fast_reply"] is True
    assert len(parameters["llm_calls"]) == 1 and parameters["llm_calls"][0]["ms"] >= 0
    assert log["latency_ms"] >= parameters["llm_calls"][0]["ms"]


def test_failed_agent_turn_logs_the_gemini_calls_made(db, agent_mode):
    set_agent_llm(ScriptedLLM([AgentUnavailableError("Aucun modèle Gemini disponible.")]))

    _ask("Mets le RPE de ma séance du jour à 5")

    parameters = json.loads(_last_log(db)["parameters"])
    assert len(parameters["llm_calls"]) == 1 and parameters["fast_reply"] is False


def test_unknown_request_goes_to_agent_with_history(db, agent_mode):
    llm = ScriptedLLM([text_turn("Première réponse."), text_turn("Je parlais bien du renfo, tu as raison.")])
    set_agent_llm(llm)

    _ask("Bonjour Otis, comment vas-tu ?", session_id="agent-history")
    _ask("Euh non, je parlais de l'autre truc", session_id="agent-history")

    second_contents = llm.requests[1]["contents"]
    assert [c["role"] for c in second_contents] == ["user", "model", "user"]


def test_fast_path_shopping_and_meals_stay_on_legacy(db, agent_mode, isolate_test_environment):
    set_agent_llm(ScriptedLLM([]))  # tout appel au LLM ferait échouer le test

    add = _ask("Ajoute mouchoirs")
    meals = _ask("Qu'est-ce qu'on mange aujourd'hui ?")

    assert add["intent"]["intent"] == "add_shopping_item"
    assert meals["intent"]["intent"] == "get_meal_plan"


def test_legacy_mode_never_calls_the_agent(db, monkeypatch):
    monkeypatch.setattr(settings, "nlu_mode", "legacy")
    db.add_sport_session({"date": TODAY, "type_seance": "EF", "statut": "Réalisé"})
    set_agent_llm(ScriptedLLM([]))

    body = _ask("Mets le RPE de ma séance d'aujourd'hui à 5")

    assert body["intent"]["intent"] == "update_sport_session"


def test_agent_unavailable_gives_explicit_answer_without_legacy_fallback(db, agent_mode):
    session_id = db.add_sport_session({"date": TODAY, "type_seance": "EF", "statut": "Réalisé"})
    set_agent_llm(ScriptedLLM([AgentUnavailableError("Aucun modèle Gemini disponible : m1 : HTTP 503.")]))

    body = _ask("Mets le RPE de ma séance d'aujourd'hui à 5")

    assert body["success"] is False
    assert "indisponible" in body["spoken_response"]
    assert db.get_sport_session_by_id(session_id)["ressenti_rpe"] is None
    assert "HTTP 503" in _last_log(db)["error_trace"]


@pytest.fixture
def gemini_writes_every_reply(monkeypatch):
    """Désactive la réponse directe de l'application : le 2e appel Gemini a lieu (et peut échouer)."""
    monkeypatch.setattr("app.core.agent.agent_service.fast_reply", lambda query, executions: None)


def test_failure_after_a_mutation_is_reported_to_the_user(db, agent_mode, gemini_writes_every_reply):
    session_id = db.add_sport_session({"date": TODAY, "type_seance": "EF", "statut": "Réalisé"})
    set_agent_llm(ScriptedLLM([
        call_turn({"name": "update_sport_session", "args": {"session_id": session_id, "changes": {"ressenti_rpe": 6}}}),
        AgentUnavailableError("Aucun modèle Gemini disponible."),
    ]))

    body = _ask("RPE 6 pour aujourd'hui")

    assert body["success"] is False
    assert "1 modification" in body["spoken_response"]
    assert body["data"]["session"]["id"] == session_id


def test_note_saved_by_agent_exposes_note_id_for_undo_toast(db, agent_mode):
    set_agent_llm(ScriptedLLM([
        call_turn({"name": "save_note", "args": {"content": "Revoir le ciblage des séances", "category": "bug_report"}}),
        text_turn("C'est noté dans tes bugs."),
    ]))

    body = _ask("Prends note de ces derniers échanges, il faudra corriger")

    assert body["data"]["note_id"] is not None
    assert body["data"]["category"] == "bug_report"


def test_note_on_previous_exchange_contains_its_exact_text(db, agent_mode):
    set_agent_llm(ScriptedLLM([
        text_turn("Ta dernière renfo date de vendredi, RPE 5."),
        call_turn({"name": "save_note", "args": {
            "content": "Date de la dernière renfo à vérifier.", "category": "bug_report", "inclure_dernier_echange": True,
        }}),
        text_turn("C'est noté."),
    ]))
    _ask("Quelle était ma dernière séance de renfo ?")

    body = _ask("Note ces derniers échanges, il faudra corriger ça")

    content = db.get_note(body["data"]["note_id"])["content"]
    assert content.endswith(
        "Toi : Quelle était ma dernière séance de renfo ?\nOtis : Ta dernière renfo date de vendredi, RPE 5."
    )


def test_add_sentence_about_sport_goes_to_agent_not_shopping(db, agent_mode, isolate_test_environment):
    """« Ajoute une séance… » est classé add_shopping_item par les regex : il ne doit jamais finir en courses."""
    set_agent_llm(ScriptedLLM([text_turn("Quel type de séance et pour quel jour ?")]))

    body = _ask("Ajoute une séance de fractionné demain")

    assert body["intent"]["intent"] == "agent"
    isolate_test_environment.add_shopping_item.assert_not_called()
    isolate_test_environment.add_shopping_items.assert_not_called()


def _agent_update_turn(session_id: int, rpe: int):
    """Modification simple : un seul appel Gemini, la réponse est rédigée par l'application."""
    return [
        call_turn({"name": "update_sport_session", "args": {"session_id": session_id, "changes": {"ressenti_rpe": rpe}}}),
    ]


def test_plain_undo_restores_agent_mutation_without_calling_the_llm(db, agent_mode):
    session_id = db.add_sport_session({"date": TODAY, "type_seance": "EF", "statut": "Réalisé"})
    llm = ScriptedLLM(_agent_update_turn(session_id, 5))  # aucun tour prévu pour l'annulation
    set_agent_llm(llm)
    _ask("Mets le RPE de ma séance du jour à 5", session_id="undo-1")

    body = _ask("Annule ce que tu viens de faire", session_id="undo-1")

    assert body["success"] is True
    assert body["intent"]["intent"] == "undo_last_action"
    assert "restaurée" in body["spoken_response"]
    assert body["data"]["undone_action"]["restored"] == [f"séance EF du {TODAY[8:10]}/{TODAY[5:7]} restaurée"]
    assert body["data"]["session"]["id"] == session_id
    assert db.get_sport_session_by_id(session_id)["ressenti_rpe"] is None
    assert len(llm.requests) == 1


def test_undo_survives_a_server_restart(db, agent_mode):
    session_id = db.add_sport_session({"date": TODAY, "type_seance": "EF", "statut": "Réalisé"})
    set_agent_llm(ScriptedLLM(_agent_update_turn(session_id, 7)))
    _ask("Mets le RPE de ma séance du jour à 7", session_id="undo-restart")

    get_session_manager().clear_all()  # équivalent d'un redémarrage d'instance Cloud Run
    body = _ask("annule ça", session_id="undo-restart")

    assert body["success"] is True
    assert db.get_sport_session_by_id(session_id)["ressenti_rpe"] is None


def test_undo_after_a_legacy_shopping_add_cancels_the_shopping_add(db, agent_mode, isolate_test_environment):
    session_id = db.add_sport_session({"date": TODAY, "type_seance": "EF", "statut": "Réalisé"})
    set_agent_llm(ScriptedLLM(_agent_update_turn(session_id, 5)))
    _ask("Mets le RPE de ma séance du jour à 5", session_id="undo-mixed")
    _ask("Ajoute lessive", session_id="undo-mixed")

    _ask("annule ça", session_id="undo-mixed")

    isolate_test_environment.remove_shopping_item.assert_called_once()
    assert db.get_sport_session_by_id(session_id)["ressenti_rpe"] == 5


def test_compound_undo_and_note_through_agent_tools(db, agent_mode):
    session_id = db.add_sport_session({"date": TODAY, "type_seance": "EF", "statut": "Réalisé"})
    set_agent_llm(ScriptedLLM(_agent_update_turn(session_id, 4) + [
        call_turn(
            {"name": "undo_last_action", "args": {}},
            {"name": "save_note", "args": {"content": "Correctif : mauvaise séance modifiée", "category": "bug_report"}},
        ),
        text_turn("J'ai annulé et noté le correctif."),
    ]))
    _ask("Mets le RPE de ma séance du jour à 4", session_id="undo-compound")

    body = _ask(
        "Annule ce que tu viens de faire. Et prends note pour un correctif : tu n'as pas modifié la bonne séance.",
        session_id="undo-compound",
    )

    assert body["success"] is True
    assert db.get_sport_session_by_id(session_id)["ressenti_rpe"] is None
    assert db.get_note(body["data"]["note_id"])["category"] == "bug_report"


def test_undo_with_nothing_to_undo_is_explicit(db, agent_mode):
    set_agent_llm(ScriptedLLM([]))
    body = _ask("annule ça", session_id="undo-empty")
    assert body["success"] is False
    assert "Aucune action" in body["spoken_response"]


def test_failure_message_after_mutation_offers_undo(db, agent_mode, gemini_writes_every_reply):
    session_id = db.add_sport_session({"date": TODAY, "type_seance": "EF", "statut": "Réalisé"})
    set_agent_llm(ScriptedLLM([
        call_turn({"name": "update_sport_session", "args": {"session_id": session_id, "changes": {"ressenti_rpe": 6}}}),
        AgentUnavailableError("Aucun modèle Gemini disponible."),
    ]))
    body = _ask("RPE 6 pour aujourd'hui", session_id="undo-after-failure")
    assert "annule" in body["spoken_response"]

    _ask("annule ça", session_id="undo-after-failure")
    assert db.get_sport_session_by_id(session_id)["ressenti_rpe"] is None


# --- Étape 5 : courses & repas -----------------------------------------------------------------------------------

@pytest.fixture
def meals_sheet():
    from app.connectors.sheets.meals_connector import MealsShoppingConnector
    from app.core.dependencies import set_meals_connector
    from tests.meals_fakes import MealsSheetState, build_meals_spreadsheet

    sheet = build_meals_spreadsheet(MealsSheetState(today=date.today(), waiting=[("Lait", False), ("Pain", False)]))
    set_meals_connector(MealsShoppingConnector(spreadsheet=sheet))
    return sheet


def test_shopping_action_goes_to_the_agent_with_meals_tools(db, agent_mode, meals_sheet):
    from tests.meals_fakes import waiting_rows

    llm = ScriptedLLM([
        call_turn({"name": "remove_shopping_items", "args": {"noms": ["pain"]}}),
        text_turn("J'ai retiré le pain de la liste."),
    ])
    set_agent_llm(llm)

    body = _ask("Enlève le pain de la liste de courses", session_id="meals-remove")

    assert body["intent"]["intent"] == "agent"
    assert waiting_rows(meals_sheet) == [("Lait", False)]
    declared = {d["name"] for d in llm.requests[0]["tools"]}
    assert {"get_shopping_list", "add_shopping_items", "check_shopping_items", "remove_shopping_items",
            "clear_bought_shopping_items", "get_meal_plan", "set_meal", "get_recipe"} <= declared


def test_agent_shopping_add_shows_undo_toast_and_plain_undo_restores(db, agent_mode, meals_sheet):
    from tests.meals_fakes import waiting_rows

    set_agent_llm(ScriptedLLM([
        call_turn({"name": "add_shopping_items", "args": {"articles": [{"nom": "beurre"}]}}),
        text_turn("Beurre ajouté au rayon Frais."),
    ]))
    added = _ask("Ajoute du beurre pour ce soir", session_id="meals-undo")
    assert [it["nom"] for it in added["data"]["items"]] == ["Beurre"]  # toast « 1 article(s) ajouté(s) »

    undone = _ask("annule ça", session_id="meals-undo")

    assert "Beurre" in undone["spoken_response"]
    assert waiting_rows(meals_sheet) == [("Lait", False), ("Pain", False)]


def test_pwa_phrases_stay_on_the_fast_lane(db, agent_mode, meals_sheet):
    set_agent_llm(ScriptedLLM([]))  # tout appel au LLM ferait échouer le test

    for query, intent in [
        ("Donne-moi la liste de courses", "get_shopping_list"),
        ("Qu'est-ce qu'on mange aujourd'hui ?", "get_meal_plan"),
        ("Vide la liste de courses", "clear_shopping_list"),
    ]:
        assert _ask(query, session_id="pwa")["intent"]["intent"] == intent


def test_short_answer_to_an_agent_question_goes_back_to_the_agent(db, agent_mode, meals_sheet):
    llm = ScriptedLLM([
        text_turn("La raclette n'est pas dans ton carnet de recettes. Je la planifie quand même demain soir ?"),
        text_turn("C'est planifié."),
    ])
    set_agent_llm(llm)

    _ask("Mets une raclette demain soir", session_id="meals-confirm")
    body = _ask("D'accord", session_id="meals-confirm")

    assert body["intent"]["intent"] == "agent"
    assert len(llm.requests) == 2


def test_small_talk_without_pending_agent_question_stays_local(db, agent_mode, meals_sheet):
    set_agent_llm(ScriptedLLM([text_turn("J'ai retiré le pain.")]))

    _ask("Enlève le pain de la liste de courses", session_id="meals-thanks")
    body = _ask("Merci", session_id="meals-thanks")

    assert body["intent"]["intent"] == "small_talk"


def test_agent_turn_discards_a_stale_legacy_pending_action(db, agent_mode, meals_sheet):
    set_agent_llm(ScriptedLLM([text_turn("Quel plat veux-tu demain ?")]))
    session = get_session_manager().get_session("meals-stale")
    session["pending_action"] = {"type": "clarify_shopping_rayon", "item": "Papier cadeau", "suggested_rayons": ["Divers"]}

    _ask("Change le menu de demain", session_id="meals-stale")

    assert "pending_action" not in get_session_manager().get_session("meals-stale")


def test_off_book_dish_is_only_planned_after_the_user_confirms(db, agent_mode, meals_sheet):
    from tests.meals_fakes import planned_meals

    tomorrow = date.today() + timedelta(days=1)
    set_meal = {"name": "set_meal", "args": {"date": tomorrow.isoformat(), "moment": "soir", "plat": "Raclette", "hors_carnet_confirme": True}}
    set_agent_llm(ScriptedLLM([
        call_turn(set_meal), text_turn("La raclette n'est pas dans ton carnet. Je la planifie quand même ?"),
        call_turn(set_meal), text_turn("C'est planifié pour demain soir."),
    ]))
    key = tomorrow.strftime("%d/%m/%Y")

    _ask("Mets une raclette demain soir", session_id="meals-offbook")
    assert planned_meals(meals_sheet)[key][1] == ""

    _ask("Oui, vas-y.", session_id="meals-offbook")
    assert planned_meals(meals_sheet)[key][1] == "Raclette"


def test_agent_unknown_article_question_is_asked_by_the_app_and_answered_without_llm(db, agent_mode, meals_sheet):
    from app.core.llm.rayon_suggester import set_rayon_suggester
    from tests.meals_fakes import waiting_rows

    async def suggester(article, rayons):
        return ["Entretien", "Épicerie"]

    set_rayon_suggester(suggester)
    llm = ScriptedLLM([
        call_turn({"name": "add_shopping_items", "args": {"articles": [{"nom": "beurre"}, {"nom": "papier cadeau"}]}}),
        text_turn("J'ai ajouté le beurre."),
    ])
    set_agent_llm(llm)

    body = _ask("Pour Noël il faudra du beurre et du papier cadeau", session_id="meals-rayon")

    assert body["spoken_response"] == (
        "J'ai ajouté le beurre. Je ne connais pas encore le rayon de « Papier cadeau » : "
        "je le range en Entretien ou en Épicerie ?"
    )
    assert waiting_rows(meals_sheet)[-1] == ("Beurre", False)

    answer = _ask("En entretien", session_id="meals-rayon")  # aucun tour LLM restant : traité par le code

    assert answer["intent"]["intent"] == "choose_rayon"
    assert waiting_rows(meals_sheet)[-1] == ("Papier cadeau", False)
    assert meals_sheet.worksheet("Ingredients_Rayons").get_all_values()[-1] == ["Papier cadeau", "Entretien"]
    assert len(llm.requests) == 2

    _ask("annule ça", session_id="meals-rayon")

    assert waiting_rows(meals_sheet)[-1] == ("Beurre", False)
    assert meals_sheet.worksheet("Ingredients_Rayons").get_all_values()[-1] != ["Papier cadeau", "Entretien"]
