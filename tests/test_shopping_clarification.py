"""Article au rayon inconnu via /interact : question, réponse enregistrée dans Ingredients_Rayons (Phase 6.8).

Même comportement en mode legacy et en mode agent (voie rapide « ajoute X ») : la réponse est traitée par le code,
sans LLM. Classeur simulé en mémoire (données fictives).
"""
from datetime import date
from typing import List, Sequence

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.connectors.sheets.meals_connector import MealsShoppingConnector
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.factory import set_agent_llm
from app.core.dependencies import set_meals_connector, set_sport_connector
from app.core.llm.rayon_suggester import set_rayon_suggester
from app.core.session_manager import get_session_manager
from app.main import app
from tests.agent_fakes import ScriptedLLM
from tests.meals_fakes import MealsSheetState, build_meals_spreadsheet, waiting_rows


class FakeSuggester:
    def __init__(self, suggestions: Sequence[str] = ("Entretien", "Épicerie")) -> None:
        self.suggestions = list(suggestions)

    async def __call__(self, article: str, rayons: Sequence[str]) -> List[str]:
        return list(self.suggestions)


@pytest.fixture(params=["legacy", "agent"])
def mode(request, monkeypatch, isolate_sqlite_database):
    monkeypatch.setattr(settings, "nlu_mode", request.param)
    set_sport_connector(SqlSportConnector(db_manager=isolate_sqlite_database))
    set_agent_llm(ScriptedLLM([]))  # la voie rapide et la réponse au rayon ne doivent jamais appeler l'agent
    set_rayon_suggester(FakeSuggester())
    yield request.param
    get_session_manager().clear_all()  # question en attente : ne doit pas fuir vers le test suivant
    set_sport_connector(None)
    set_agent_llm(None)


@pytest.fixture
def sheet():
    sheet = build_meals_spreadsheet(MealsSheetState(today=date.today(), waiting=[("Pain", False)]))
    set_meals_connector(MealsShoppingConnector(spreadsheet=sheet))
    return sheet


def _ask(query: str, session_id: str = "rayon-test") -> dict:
    resp = TestClient(app).post("/api/v1/interact", json={"query": query, "session_id": session_id})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ingredient_rows(sheet):
    return [tuple(row) for row in sheet.worksheet("Ingredients_Rayons").get_all_values()[1:]]


def test_known_article_is_added_without_question(mode, sheet):
    body = _ask("Ajoute du lait")

    assert waiting_rows(sheet)[-1] == ("Lait", False)
    assert "?" not in body["spoken_response"]


def test_unknown_article_triggers_a_question_with_two_rayons_and_nothing_is_added(mode, sheet):
    body = _ask("Ajoute du papier cadeau")

    assert body["spoken_response"] == (
        "Je ne connais pas encore le rayon de « Papier cadeau » : je le range en Entretien ou en Épicerie ?"
    )
    assert body["data"]["rayon_question"]["article"] == "Papier cadeau"
    assert waiting_rows(sheet) == [("Pain", False)]


def test_open_question_when_no_rayon_can_be_suggested(mode, sheet):
    set_rayon_suggester(FakeSuggester([]))

    body = _ask("Ajoute du papier cadeau")

    assert body["spoken_response"].endswith("dans quel rayon je le range ?")


def test_known_articles_are_added_and_the_unknown_one_is_asked(mode, sheet):
    body = _ask("Ajoute du lait et du papier cadeau")

    assert waiting_rows(sheet)[-1] == ("Lait", False)
    assert "Lait" in body["spoken_response"] and "« Papier cadeau »" in body["spoken_response"]


def test_chosen_rayon_is_saved_and_never_asked_again(mode, sheet):
    _ask("Ajoute du papier cadeau")

    body = _ask("En entretien")

    assert body["intent"]["intent"] == "choose_rayon"
    assert "Entretien" in body["spoken_response"]
    assert _ingredient_rows(sheet)[-1] == ("Papier cadeau", "Entretien")
    assert waiting_rows(sheet)[-1] == ("Papier cadeau", False)
    assert len(body["data"]["items"]) == 1  # toast « article(s) ajouté(s) »

    again = _ask("Ajoute du papier cadeau", session_id="rayon-autre-session")
    assert "?" not in again["spoken_response"]


def test_divers_reply_is_saved_as_divers(mode, sheet):
    _ask("Ajoute du papier cadeau")

    _ask("Laisse en divers")

    assert _ingredient_rows(sheet)[-1] == ("Papier cadeau", "Divers")


def test_cancel_reply_adds_and_saves_nothing(mode, sheet):
    rows_before = _ingredient_rows(sheet)
    _ask("Ajoute du papier cadeau")

    body = _ask("Non annule")

    assert body["spoken_response"] == "D'accord, je n'ajoute pas Papier cadeau."
    assert _ingredient_rows(sheet) == rows_before
    assert waiting_rows(sheet) == [("Pain", False)]


def test_new_request_sets_the_article_aside_then_is_handled(mode, sheet):
    _ask("Ajoute du papier cadeau")

    body = _ask("Donne-moi la liste de courses")

    assert body["spoken_response"].startswith(
        "J'ai ajouté Papier cadeau, son rayon sera à trier plus tard dans votre sheet. "
    )
    assert body["intent"]["intent"] == "get_shopping_list"
    assert _ingredient_rows(sheet)[-1] == ("Papier cadeau", "")
    assert waiting_rows(sheet)[-1] == ("Papier cadeau", False)


def test_short_unrelated_reply_only_sets_the_article_aside(mode, sheet):
    _ask("Ajoute du papier cadeau")

    body = _ask("Euh je sais pas")

    assert body["spoken_response"] == "J'ai ajouté Papier cadeau, son rayon sera à trier plus tard dans votre sheet."
    assert "rayon_question" not in get_session_manager().get_session("rayon-test")


def test_queued_unknown_articles_are_asked_one_after_the_other(mode, sheet):
    _ask("Ajoute du papier cadeau et des bougies")

    body = _ask("Le premier")

    assert body["spoken_response"].endswith("Je ne connais pas encore le rayon de « Bougies » : je le range en Entretien ou en Épicerie ?")
    _ask("Épicerie")
    assert _ingredient_rows(sheet)[-2:] == [("Papier cadeau", "Entretien"), ("Bougies", "Épicerie")]


def test_undo_after_the_answer_removes_the_article(mode, sheet):
    rows_before = _ingredient_rows(sheet)
    _ask("Ajoute du papier cadeau")
    _ask("En entretien")

    _ask("annule ça")

    assert waiting_rows(sheet) == [("Pain", False)]
    if mode == "agent":  # annulation exacte par le journal : le rayon appris est aussi oublié
        assert _ingredient_rows(sheet) == rows_before
