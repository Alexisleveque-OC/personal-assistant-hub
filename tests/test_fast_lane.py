"""Voie rapide regex du mode agent (Phase 6.8 - Étape 5) : seules les demandes simples et non ambiguës évitent Gemini."""
import pytest

from app.core.intent_parser import IntentParser
from app.core.models import IntentType
from app.handlers.fast_lane import FAST_LANE_INTENTS, is_fast_lane

parser = IntentParser()


@pytest.mark.parametrize("query", [
    # Phrases envoyées telles quelles par la PWA (vues Courses et Repas) : doivent rester instantanées.
    "Donne-moi la liste de courses",
    "Qu'est-ce qu'on mange aujourd'hui ?",
    "Vide la liste de courses",
    # Demandes simples.
    "Ajoute du lait",
    "Ajoute mouchoirs",
    "Ajoute du lait et des œufs à la liste de courses",
    "Rajoute 2 paquets de café",
    "Qu'est-ce qu'on mange ce soir ?",
    "On mange quoi demain midi ?",
    "Il me reste quoi à acheter ?",
    "Qu'est-ce qu'il me reste à acheter au rayon frais ?",
    "Donne-moi la liste d'attente",
])
def test_simple_requests_stay_on_the_fast_lane(query):
    parsed = parser.parse(query)
    assert parsed.intent in FAST_LANE_INTENTS, parsed.intent
    assert is_fast_lane(parsed, query)


@pytest.mark.parametrize("query, captured_as", [
    # « ajoute X » qui n'est pas (seulement) un article de courses.
    ("Ajoute une séance de fractionné demain", IntentType.ADD_SHOPPING_ITEM),
    ("Ajoute des lasagnes au menu de demain soir", IntentType.GET_MEAL_PLAN),
    ("Ajoute de la crème solaire au rayon hygiène", IntentType.ADD_SHOPPING_ITEM),
    ("Rajoute du pain, et coche le lait", IntentType.ADD_SHOPPING_ITEM),
    ("Ajoute que je dois rappeler le garagiste", IntentType.ADD_SHOPPING_ITEM),
    ("Ajoute du beurre au lieu de la margarine", IntentType.ADD_SHOPPING_ITEM),
    # « liste de courses » dans une demande d'action ou une question précise.
    ("Enlève le pain de la liste de courses", IntentType.GET_SHOPPING_LIST),
    ("Est-ce qu'il reste du café sur la liste de courses ?", IntentType.GET_SHOPPING_LIST),
    ("Coche le lait sur la liste de courses", IntentType.GET_SHOPPING_LIST),
    # « qu'est-ce qu'on mange » composé ou portant sur plusieurs jours.
    ("Qu'est-ce qu'on mange ce midi et ce soir ?", IntentType.GET_MEAL_PLAN),
    ("Qu'est-ce qu'on mange cette semaine ?", IntentType.GET_MEAL_PLAN),
    ("Change le menu de jeudi", IntentType.GET_MEAL_PLAN),
    # Vider avec une nuance.
    ("Vide la liste de courses sauf le lait", IntentType.CLEAR_SHOPPING_LIST),
])
def test_ambiguous_or_compound_requests_leave_the_fast_lane(query, captured_as):
    parsed = parser.parse(query)
    assert parsed.intent == captured_as, f"la regex ne capte plus « {query} » : cas de test à revoir"
    assert not is_fast_lane(parsed, query)


def test_other_intents_are_never_fast_lane():
    parsed = parser.parse("Mets le RPE de ma séance du jour à 5")
    assert not is_fast_lane(parsed, "Mets le RPE de ma séance du jour à 5")
