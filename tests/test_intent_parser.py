"""Tests unitaires du moteur de classification d'intentions (NLU)."""
import pytest
from app.core.intent_parser import IntentParser
from app.core.models import IntentType

parser = IntentParser()


@pytest.mark.parametrize(
    "phrase,expected_intent,expected_params",
    [
        ("Qu'est-ce qu'on mange ce soir ?", IntentType.GET_MEAL_PLAN, {"period": "soir"}),
        ("On mange quoi demain ?", IntentType.GET_MEAL_PLAN, {"period": "demain"}),
        ("Ajoute du café bio à la liste de courses", IntentType.ADD_SHOPPING_ITEM, {"item": "du café bio"}),
        ("Mets des pâtes sur la liste de courses", IntentType.ADD_SHOPPING_ITEM, {"item": "des pâtes"}),
        ("Donne-moi la liste de courses", IntentType.GET_SHOPPING_LIST, {}),
        ("Combien il reste de budget courses pour ce mois ?", IntentType.GET_BUDGET_BALANCE, {"category": "courses"}),
        ("Quel est le solde restant ?", IntentType.GET_BUDGET_BALANCE, {"category": "general"}),
        ("J'ai acheté pour 42.50 euros de courses", IntentType.LOG_EXPENSE, {"amount": 42.5, "category": "courses"}),
        ("Dépensé 15€ en loisir", IntentType.LOG_EXPENSE, {"amount": 15.0, "category": "loisir"}),
        ("Rappelle-moi d'appeler le garagiste", IntentType.ADD_TASK, {"task": "appeler le garagiste"}),
        ("Quelles sont mes tâches aujourd'hui ?", IntentType.LIST_TASKS, {}),
        ("Résume mes mails importants", IntentType.SUMMARIZE_EMAILS, {}),
        ("Allume la prise du salon", IntentType.TOGGLE_DEVICE, {"device": "prise", "action": "on"}),
        ("Éteins la prise", IntentType.TOGGLE_DEVICE, {"device": "prise", "action": "off"}),
    ],
)
def test_intent_parser_known_cases(phrase, expected_intent, expected_params):
    parsed = parser.parse(phrase)
    assert parsed.intent == expected_intent
    for key, expected_val in expected_params.items():
        assert parsed.parameters.get(key) == expected_val


def test_intent_parser_unknown():
    parsed = parser.parse("Quel temps fait-il sur Mars ?")
    assert parsed.intent == IntentType.UNKNOWN
    assert parsed.confidence < 0.5
