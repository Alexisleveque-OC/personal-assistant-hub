"""Question « dans quel rayon ? » pour un article inconnu, réponse enregistrée dans Ingredients_Rayons (Phase 6.8).

Logique unique partagée par la voie rapide regex et l'outil agent `add_shopping_items`.
"""
from datetime import date
from typing import List, Sequence

import pytest

from app.connectors.sheets.meals_connector import MealsShoppingConnector
from app.core.agent.tools.meals_models import RayonLearnedUndo, ShoppingAddedUndo
from app.core.agent.tools.meals_tools import MealsTools, MealsToolError
from app.core.shopping.rayon_questions import PendingRayonQuestion, RayonQuestions, interpret_reply
from tests.meals_fakes import DEFAULT_RAYONS, MealsSheetState, build_meals_spreadsheet, waiting_rows

TODAY = date(2026, 10, 21)
RAYONS = list(DEFAULT_RAYONS)


class FakeSuggester:
    def __init__(self, suggestions: Sequence[str] = ("Entretien", "Épicerie")) -> None:
        self.suggestions = list(suggestions)
        self.calls: List[str] = []

    async def __call__(self, article: str, rayons: Sequence[str]) -> List[str]:
        self.calls.append(article)
        return list(self.suggestions)


@pytest.fixture
def sheet():
    return build_meals_spreadsheet(MealsSheetState(today=TODAY, waiting=[("Pain", False)]))


@pytest.fixture
def connector(sheet):
    return MealsShoppingConnector(spreadsheet=sheet)


def _ingredient_rows(sheet):
    return [tuple(row) for row in sheet.worksheet("Ingredients_Rayons").get_all_values()[1:]]


# --- Interprétation de la réponse (déterministe, sans LLM) -------------------------------------------------------

@pytest.mark.parametrize("reply, rayon", [
    ("En entretien", "Entretien"),
    ("Range-le à l'épicerie", "Épicerie"),
    ("fruits et légumes", "Fruits & Légumes"),
    ("au rayon surgelé", "Surgelés"),
    ("Non, plutôt en hygiène", "Hygiène"),
    ("le premier", "Entretien"),
    ("La deuxième", "Épicerie"),
    ("Laisse en divers", "Divers"),
])
def test_reply_naming_a_rayon_of_the_sheet_is_recognized(reply, rayon):
    result = interpret_reply(reply, RAYONS, ["Entretien", "Épicerie"])

    assert (result.kind, result.rayon) == ("rayon", rayon)


def test_divers_is_accepted_even_when_absent_from_the_rayons_tab():
    assert interpret_reply("divers", ["Frais", "Épicerie"], []).rayon == "Divers"


def test_partial_rayon_name_matches_when_unambiguous():
    rayons = ["PQ + entretien", "Épicerie", "Fruits & Légumes", "Légumes surgelés"]

    assert interpret_reply("en entretien", rayons, []).rayon == "PQ + entretien"
    assert interpret_reply("légumes", rayons, []).kind == "unrecognized"
    assert interpret_reply("surgelé", ["Surgelés", "Légumes surgelés"], []).rayon == "Surgelés"


def test_a_new_request_mentioning_a_rayon_word_is_not_a_rayon_choice():
    assert interpret_reply("ajoute aussi du lait frais", RAYONS, []).kind == "unrecognized"


@pytest.mark.parametrize("reply", ["Non", "Annule", "laisse tomber", "non merci"])
def test_cancel_replies(reply):
    assert interpret_reply(reply, RAYONS, ["Entretien", "Épicerie"]).kind == "cancel"


@pytest.mark.parametrize("reply", ["je sais pas", "qu'est-ce qu'on mange ce soir ?", "le premier"])
def test_other_replies_are_unrecognized(reply):
    assert interpret_reply(reply, RAYONS, []).kind == "unrecognized"


# --- Question --------------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_question_offers_two_suggestions_and_queues_the_other_articles(connector, sheet):
    suggester = FakeSuggester()

    pending, question = await RayonQuestions(connector, suggester).ask(["papier cadeau", "des bougies"])

    assert pending == PendingRayonQuestion(article="Papier cadeau", suggestions=["Entretien", "Épicerie"], queue=["Bougies"])
    assert question == "Je ne connais pas encore le rayon de « Papier cadeau » : je le range en Entretien ou en Épicerie ?"
    assert suggester.calls == ["Papier cadeau"]
    assert waiting_rows(sheet) == [("Pain", False)]  # rien d'ajouté avant la réponse


@pytest.mark.asyncio
async def test_question_is_open_without_suggestions(connector):
    _, question = await RayonQuestions(connector, FakeSuggester([])).ask(["Bougies"])

    assert question == "Je ne connais pas encore le rayon de « Bougies » : dans quel rayon je le range ?"


# --- Réponse ---------------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chosen_rayon_is_saved_then_the_article_is_added(connector, sheet):
    pending = PendingRayonQuestion(article="Papier cadeau", suggestions=["Entretien", "Épicerie"])

    answer = await RayonQuestions(connector, FakeSuggester()).answer("en entretien", pending)

    assert answer.consumed and answer.next_question is None
    assert _ingredient_rows(sheet)[-1] == ("Papier cadeau", "Entretien")
    assert waiting_rows(sheet)[-1] == ("Papier cadeau", False)
    assert [(it.item, it.rayon) for it in answer.added] == [("Papier cadeau", "Entretien")]
    assert answer.undos == [RayonLearnedUndo(ingredient="Papier cadeau", rayon="Entretien"), ShoppingAddedUndo(items=["Papier cadeau"])]
    assert answer.spoken == "C'est noté, Papier cadeau est ajouté au rayon Entretien, je m'en souviendrai."
    # La question n'est posée qu'une fois : l'article est désormais connu.
    assert connector.resolve_rayon("papier cadeau") == ("Entretien", None)


@pytest.mark.asyncio
async def test_divers_is_saved_as_divers(connector, sheet):
    answer = await RayonQuestions(connector, FakeSuggester()).answer("divers", PendingRayonQuestion(article="Bougies"))

    assert _ingredient_rows(sheet)[-1] == ("Bougies", "Divers")
    assert answer.consumed


@pytest.mark.asyncio
async def test_answer_asks_the_next_queued_article(connector, sheet):
    suggester = FakeSuggester(["Hygiène", "Entretien"])
    pending = PendingRayonQuestion(article="Papier cadeau", suggestions=["Entretien", "Épicerie"], queue=["Bougies"])

    answer = await RayonQuestions(connector, suggester).answer("le premier", pending)

    assert answer.next_question == PendingRayonQuestion(article="Bougies", suggestions=["Hygiène", "Entretien"])
    assert answer.spoken.endswith("Je ne connais pas encore le rayon de « Bougies » : je le range en Hygiène ou en Entretien ?")
    assert waiting_rows(sheet)[-1] == ("Papier cadeau", False)


@pytest.mark.asyncio
async def test_cancel_adds_and_saves_nothing_including_the_queue(connector, sheet):
    rows_before = _ingredient_rows(sheet)
    pending = PendingRayonQuestion(article="Papier cadeau", queue=["Bougies"])

    answer = await RayonQuestions(connector, FakeSuggester()).answer("non, annule", pending)

    assert answer.consumed and answer.next_question is None and answer.undos == []
    assert answer.spoken == "D'accord, je n'ajoute pas Papier cadeau et Bougies."
    assert _ingredient_rows(sheet) == rows_before
    assert waiting_rows(sheet) == [("Pain", False)]


@pytest.mark.asyncio
async def test_unrecognized_reply_sets_the_articles_aside_to_be_sorted_in_the_sheet(connector, sheet):
    pending = PendingRayonQuestion(article="Papier cadeau", queue=["Bougies"])

    answer = await RayonQuestions(connector, FakeSuggester()).answer("qu'est-ce qu'on mange ce soir ?", pending)

    assert not answer.consumed and answer.next_question is None
    assert _ingredient_rows(sheet)[-2:] == [("Papier cadeau", ""), ("Bougies", "")]
    assert waiting_rows(sheet)[-2:] == [("Papier cadeau", False), ("Bougies", False)]
    assert answer.spoken == "J'ai ajouté Papier cadeau et Bougies, leur rayon sera à trier plus tard dans votre sheet."
    assert connector.resolve_rayon("Bougies") == ("Divers", None)


@pytest.mark.asyncio
async def test_single_article_set_aside_message_is_singular(connector):
    answer = await RayonQuestions(connector, FakeSuggester()).answer("je sais pas", PendingRayonQuestion(article="Bougies"))

    assert answer.spoken == "J'ai ajouté Bougies, son rayon sera à trier plus tard dans votre sheet."


# --- Annulation exacte du rayon appris -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_learned_rayon_undo_removes_the_row_and_the_article(connector, sheet):
    rows_before, waiting_before = _ingredient_rows(sheet), waiting_rows(sheet)
    answer = await RayonQuestions(connector, FakeSuggester()).answer("entretien", PendingRayonQuestion(article="Papier cadeau"))
    tools = MealsTools(connector)

    for undo in reversed(answer.undos):
        tools.check_undo(undo)
        tools.apply_undo(undo)

    assert _ingredient_rows(sheet) == rows_before
    assert waiting_rows(sheet) == waiting_before
    assert connector.resolve_rayon("Papier cadeau")[1] is not None  # la question pourra être reposée


def test_learned_rayon_undo_is_refused_if_the_rayon_was_changed_since(connector, sheet):
    connector.learn_ingredient_rayon("Papier cadeau", "Entretien")
    ws = sheet.worksheet("Ingredients_Rayons")
    ws.update_cell(len(ws.rows), 2, "Épicerie")

    with pytest.raises(MealsToolError, match="Papier cadeau"):
        MealsTools(connector).check_undo(RayonLearnedUndo(ingredient="Papier cadeau", rayon="Entretien"))
