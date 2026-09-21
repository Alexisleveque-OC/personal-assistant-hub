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
        ("Quels sont les ingrédients pour le risotto de quinoa ?", IntentType.GET_RECIPE_INGREDIENTS, {"recipe": "risotto de quinoa"}),
        ("Qu'est-ce qu'il faut pour faire du guacamole ?", IntentType.GET_RECIPE_INGREDIENTS, {"recipe": "guacamole"}),
        ("Ajoute les ingrédients du risotto de quinoa à la liste de courses", IntentType.ADD_RECIPE_INGREDIENTS, {"recipe": "risotto de quinoa"}),
        ("Ajoute les ingrédients du guacamole sauf le citron vert", IntentType.ADD_RECIPE_INGREDIENTS, {"recipe": "guacamole", "exclude": "citron vert"}),
        ("Mets des pâtes carbonara ce soir", IntentType.SET_MEAL_PLAN, {"meal": "pâtes carbonara", "period": "soir"}),
        ("Prévois une pizza maison demain soir", IntentType.SET_MEAL_PLAN, {"meal": "pizza maison", "period": "soir"}),
        ("Ajoute du café bio à la liste de courses", IntentType.ADD_SHOPPING_ITEM, {"item": "café bio"}),
        ("Mets des pâtes sur la liste de courses", IntentType.ADD_SHOPPING_ITEM, {"item": "pâtes"}),
        ("ajoute chocolat", IntentType.ADD_SHOPPING_ITEM, {"item": "chocolat"}),
        ("Ajoute chocolat a la liste de course", IntentType.ADD_SHOPPING_ITEM, {"item": "chocolat"}),
        ("J'ai besoin de quoi pour préparer un guacamole ?", IntentType.GET_RECIPE_INGREDIENTS, {"recipe": "guacamole"}),
        ("Donnes moi la recette du préfou", IntentType.GET_RECIPE_INGREDIENTS, {"recipe": "préfou"}),
        ("Donne la recette de la tarte aux pommes", IntentType.GET_RECIPE_INGREDIENTS, {"recipe": "tarte aux pommes"}),
        ("quel est la recette pour le Chilli sin carne", IntentType.GET_RECIPE_INGREDIENTS, {"recipe": "chilli sin carne"}),
        ("quel est la recette pour le Chilli sin carne ?", IntentType.GET_RECIPE_INGREDIENTS, {"recipe": "chilli sin carne"}),
        ("quelle est la recette pour les wraps de légumes", IntentType.GET_RECIPE_INGREDIENTS, {"recipe": "wraps de légumes"}),
        ("la recette pour le risotto", IntentType.GET_RECIPE_INGREDIENTS, {"recipe": "risotto"}),
        ("Ajoute les ingrédients du Panini sans le jambon", IntentType.ADD_RECIPE_INGREDIENTS, {"recipe": "panini", "exclude": "jambon"}),
        ("ajoute les ingrédients pour faire du Boeuf aux poivrons sauf ail et oignons", IntentType.ADD_RECIPE_INGREDIENTS, {"recipe": "boeuf aux poivrons", "exclude": "ail et oignons"}),
        ("Donne-moi la liste de courses", IntentType.GET_SHOPPING_LIST, {}),
        ("J'ai acheté le café bio et le dentifrice", IntentType.MARK_SHOPPING_BOUGHT, {"items": "le café bio et le dentifrice"}),
        ("Vide la liste de courses", IntentType.CLEAR_SHOPPING_LIST, {}),
        ("Combien il reste de budget courses pour ce mois ?", IntentType.GET_BUDGET_BALANCE, {"category": "courses"}),
        ("Quel est le solde restant ?", IntentType.GET_BUDGET_BALANCE, {"category": "general"}),
        ("J'ai acheté pour 42.50 euros de courses", IntentType.LOG_EXPENSE, {"amount": 42.5, "category": "courses"}),
        ("Dépensé 15€ en loisir", IntentType.LOG_EXPENSE, {"amount": 15.0, "category": "loisir"}),
        ("Rappelle-moi d'appeler le garagiste", IntentType.ADD_TASK, {"task": "appeler le garagiste"}),
        ("Quelles sont mes tâches aujourd'hui ?", IntentType.LIST_TASKS, {}),
        ("Résume mes mails importants", IntentType.SUMMARIZE_EMAILS, {}),
        ("que mange t-on jeudi prochain ?", IntentType.GET_MEAL_PLAN, {"period": "jour", "day_name": "Jeudi"}),
        ("Qu'est ce qu'on mange Jeudi prochain ?", IntentType.GET_MEAL_PLAN, {"period": "jour", "day_name": "Jeudi"}),
        ("On mange quoi?", IntentType.GET_MEAL_PLAN, {"period": "prochain"}),
        ("J'aimerai mangé du risotto jeudi prochain", IntentType.SET_MEAL_PLAN, {"meal": "risotto", "day_name": "Jeudi"}),
        ("prévois du poulet pour jeudi", IntentType.SET_MEAL_PLAN, {"meal": "poulet", "day_name": "Jeudi"}),
        ("Allume la prise du salon", IntentType.TOGGLE_DEVICE, {"device": "prise", "action": "on"}),
        ("Éteins la prise", IntentType.TOGGLE_DEVICE, {"device": "prise", "action": "off"}),
        ("donne moi la liste d'attente", IntentType.GET_SHOPPING_LIST, {"filter": "waiting_list"}),
        ("Qu'est ce que je doit acheter ?", IntentType.GET_SHOPPING_LIST, {}),
        ("qu'est-ce qu'il faut acheter", IntentType.GET_SHOPPING_LIST, {}),
        ("J'ai acheté tout les produit de la listes d'attente", IntentType.MARK_SHOPPING_BOUGHT, {"all": True}),
        ("J'ai tout acheté", IntentType.MARK_SHOPPING_BOUGHT, {"all": True}),
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


def test_intent_parser_anaphora_with_context():
    """Vérifie la résolution des anaphores ('ces ingrédients', 'ajoute-les') via le contexte conversationnel."""
    ctx = {"last_recipe": "Orzo brocolis"}

    # 1. Ajout direct sans exclusion
    p1 = parser.parse("Ajoutes ces ingrédients", context=ctx)
    assert p1.intent == IntentType.ADD_RECIPE_INGREDIENTS
    assert p1.parameters.get("recipe") == "Orzo brocolis"
    assert "exclude" not in p1.parameters

    # 2. Ajoute-les
    p2 = parser.parse("Ajoute-les", context=ctx)
    assert p2.intent == IntentType.ADD_RECIPE_INGREDIENTS
    assert p2.parameters.get("recipe") == "Orzo brocolis"

    # 3. Ajout avec exclusion
    p3 = parser.parse("Ajoute ces ingrédients sauf le lait", context=ctx)
    assert p3.intent == IntentType.ADD_RECIPE_INGREDIENTS
    assert p3.parameters.get("recipe") == "Orzo brocolis"
    assert p3.parameters.get("exclude") == "lait"

    # 4. Mets-les sur la liste sauf ...
    p4 = parser.parse("Mets-les sur la liste sauf les champignons", context=ctx)
    assert p4.intent == IntentType.ADD_RECIPE_INGREDIENTS
    assert p4.parameters.get("recipe") == "Orzo brocolis"
    assert p4.parameters.get("exclude") == "champignons"


def test_intent_parser_anaphora_without_context():
    """Vérifie le comportement si l'utilisateur dit 'ajoute ces ingrédients' sans contexte préalable."""
    p = parser.parse("Ajoutes ces ingrédients")
    assert p.intent == IntentType.ADD_RECIPE_INGREDIENTS
    assert p.parameters.get("error") == "no_context_recipe"


def test_intent_parser_small_talk():
    """Vérifie la reconnaissance des salutations, remerciements et accusés de réception."""
    for phrase in ["ok merci", "merci", "merci beaucoup", "bonjour", "au revoir", "d'accord", "super merci", "parfait"]:
        p = parser.parse(phrase)
        assert p.intent == IntentType.SMALL_TALK, f"Échec pour '{phrase}'"


def test_intent_parser_natural_anaphora():
    """Vérifie la prise en compte des tournures naturelles : 'rajoute tout', 'tu peux tout rajouter...'."""
    ctx = {"last_recipe": "Wrap de légumes"}

    # 1. rajoute tout / ajoute tout
    p1 = parser.parse("rajoute tout", context=ctx)
    assert p1.intent == IntentType.ADD_RECIPE_INGREDIENTS
    assert p1.parameters.get("recipe") == "Wrap de légumes"

    p2 = parser.parse("ajoute tout", context=ctx)
    assert p2.intent == IntentType.ADD_RECIPE_INGREDIENTS
    assert p2.parameters.get("recipe") == "Wrap de légumes"

    p3 = parser.parse("tu peux tout rajouter a la liste d'ingrédients", context=ctx)
    assert p3.intent == IntentType.ADD_RECIPE_INGREDIENTS
    assert p3.parameters.get("recipe") == "Wrap de légumes"

    p4 = parser.parse("tu peux tout mettre sur la liste de courses", context=ctx)
    assert p4.intent == IntentType.ADD_RECIPE_INGREDIENTS
    assert p4.parameters.get("recipe") == "Wrap de légumes"

    # 3. Formules avec exclusion
    p5 = parser.parse("rajoute tout sauf la crème", context=ctx)
    assert p5.intent == IntentType.ADD_RECIPE_INGREDIENTS
    assert p5.parameters.get("recipe") == "Wrap de légumes"
    assert p5.parameters.get("exclude") == "crème"

    p6 = parser.parse("tu peux tout rajouter sauf les carottes", context=ctx)
    assert p6.intent == IntentType.ADD_RECIPE_INGREDIENTS
    assert p6.parameters.get("recipe") == "Wrap de légumes"
    assert p6.parameters.get("exclude") == "carottes"

    # 4. 'rajoute tout' sans contexte ne doit JAMAIS ajouter l'article 'tout'
    p7 = parser.parse("rajoute tout")
    assert p7.intent == IntentType.ADD_RECIPE_INGREDIENTS
    assert p7.parameters.get("error") == "no_context_recipe"


def test_intent_parser_recipe_ingredients_anaphora():
    """Anaphore demandant les ingrédients du plat mentionné précédemment."""
    parsed1 = parser.parse("quel ingredients faut-il ?", context={"last_recipe": "Risotto de quinoa"})
    assert parsed1.intent == IntentType.GET_RECIPE_INGREDIENTS
    assert parsed1.parameters.get("recipe") == "Risotto de quinoa"

    parsed2 = parser.parse("il faut quoi ?", context={"last_recipe": "Salade de lentilles"})
    assert parsed2.intent == IntentType.GET_RECIPE_INGREDIENTS
    assert parsed2.parameters.get("recipe") == "Salade de lentilles"

    parsed3 = parser.parse("quel ingredients faut-il ?", context={})
    assert parsed3.intent == IntentType.UNKNOWN


def test_intent_parser_confirm_cancel():
    """Confirmation et annulation interactive en présence d'une action en attente."""
    ctx = {"pending_action": {"type": "set_meal_plan", "meal": "poulet", "target_date": "24/09/2026"}}
    
    parsed_yes = parser.parse("oui", context=ctx)
    assert parsed_yes.intent == IntentType.CONFIRM

    parsed_vas_y = parser.parse("vas-y", context=ctx)
    assert parsed_vas_y.intent == IntentType.CONFIRM

    parsed_no = parser.parse("non", context=ctx)
    assert parsed_no.intent == IntentType.CANCEL

    parsed_annule = parser.parse("annule", context=ctx)
    assert parsed_annule.intent == IntentType.CANCEL


