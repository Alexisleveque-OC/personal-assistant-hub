"""Tests fonctionnels de l'endpoint d'interaction universel."""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from app.main import app, set_meals_connector
from app.connectors.sheets.models import (
    DayMealPlan,
    Recipe,
    WaitingListItem,
    ShoppingItem,
)

client = TestClient(app)


@pytest.fixture
def meals():
    """Connecteur repas/courses simulé et vierge (remplace celui du conftest, remis à None par lui en fin de test)."""
    connector = MagicMock()
    set_meals_connector(connector)
    return connector


def test_interact_meal_plan_fallback():
    """Sans connecteur injecté, l'endpoint répond avec le fallback gracieux."""
    set_meals_connector(None)
    response = client.post("/api/v1/interact", json={"query": "Qu'est-ce qu'on mange ce soir ?"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "repas" in data["spoken_response"].lower() or "lasagnes" in data["spoken_response"].lower()
    assert data["intent"]["intent"] == "get_meal_plan"


def test_interact_with_mocked_connector(meals):
    """Avec connecteur injecté, l'endpoint appelle les méthodes métier et renvoie la réponse adaptée."""
    meals.get_meal_plan.return_value = DayMealPlan(
        date_str="11/09/2026",
        day_name="Vendredi",
        lunch="Salade César",
        dinner="Pizza 4 fromages",
    )
    meals.get_recipe_ingredients.return_value = Recipe(
        name="Risotto de quinoa",
        category="Féculents",
        is_complete=True,
        ingredients=["Quinoa", "Champignons", "Parmesan"],
    )
    meals.add_recipe_ingredients_to_shopping_list.return_value = (
        Recipe(name="Guacamole", ingredients=["Avocat", "Épices"]),
        [
            WaitingListItem(item="Avocat", rayon="Légumes"),
            WaitingListItem(item="Épices", rayon="Épicerie"),
        ],
    )
    meals.set_meal_plan.return_value = DayMealPlan(
        date_str="11/09/2026",
        day_name="Vendredi",
        dinner="Pâtes carbonara",
    )
    meals.add_shopping_item.return_value = (
        WaitingListItem(item="Café bio", rayon="Épicerie"),
        None,
    )
    meals.get_shopping_list.return_value = {
        "waiting_list": [WaitingListItem(item="Café bio", rayon="Épicerie")],
        "current_week_items": [ShoppingItem(name="Pommes", checked=False)],
    }
    meals.mark_shopping_items_bought.return_value = ["Café bio"]
    meals.clear_shopping_list.return_value = 1


    # 1. Repas du soir
    r1 = client.post("/api/v1/interact", json={"query": "Qu'est-ce qu'on mange ce soir ?"})
    assert r1.status_code == 200
    assert "Pizza 4 fromages" in r1.json()["spoken_response"]

    # 2. Ingrédients d'une recette
    r2 = client.post("/api/v1/interact", json={"query": "Quels sont les ingrédients pour le risotto de quinoa ?"})
    assert r2.status_code == 200
    assert "Quinoa" in r2.json()["spoken_response"]
    assert "Champignons" in r2.json()["spoken_response"]

    # 3. Ajout ingrédients recette aux courses
    r3 = client.post("/api/v1/interact", json={"query": "Ajoute les ingrédients du guacamole à la liste de courses"})
    assert r3.status_code == 200
    assert "Guacamole" in r3.json()["spoken_response"]
    assert "2 article(s)" in r3.json()["spoken_response"]

    # 4. Planification d'un repas
    r4 = client.post("/api/v1/interact", json={"query": "Mets des pâtes carbonara ce soir"})
    assert r4.status_code == 200
    assert "planifié" in r4.json()["spoken_response"]

    # 5. Ajout d'article
    r5 = client.post("/api/v1/interact", json={"query": "Ajoute du café bio à la liste de courses"})
    assert r5.status_code == 200
    assert "café bio" in r5.json()["spoken_response"].lower()

    # 6. Consultation liste de courses
    r6 = client.post("/api/v1/interact", json={"query": "Donne-moi la liste de courses"})
    assert r6.status_code == 200
    assert "Café bio" in r6.json()["spoken_response"]
    assert "Pommes" in r6.json()["spoken_response"]

    # 7. Marquage acheté
    r7 = client.post("/api/v1/interact", json={"query": "J'ai acheté le café bio"})
    assert r7.status_code == 200
    assert "coché" in r7.json()["spoken_response"]

    # 8. Nettoyage liste
    r8 = client.post("/api/v1/interact", json={"query": "Vide la liste de courses"})
    assert r8.status_code == 200
    assert "nettoyée" in r8.json()["spoken_response"]

    # Nettoyage après test


def test_interact_budget_query():
    response = client.post(
        "/api/v1/interact",
        json={"query": "Combien il reste de budget courses ?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "budget courses" in data["spoken_response"]


def test_interact_conversational_anaphora_followup(meals):
    """Vérifie le chaînage conversationnel : consultation de recette puis 'Ajoutes ces ingrédients'."""
    meals.get_recipe_ingredients.return_value = Recipe(
        name="Orzo brocolis",
        ingredients=["Orzo", "Brocolis", "Champignons", "Poitrine", "Lait"],
    )
    meals.add_recipe_ingredients_to_shopping_list.return_value = (
        Recipe(name="Orzo brocolis", ingredients=["Orzo", "Brocolis", "Champignons", "Poitrine", "Lait"]),
        [
            WaitingListItem(item="Orzo", rayon="Féculents"),
            WaitingListItem(item="Brocolis", rayon="Légumes"),
            WaitingListItem(item="Poitrine", rayon="Boucherie"),
            WaitingListItem(item="Lait", rayon="Frais"),
        ],
    )

    # 1. Première requête : consultation de recette
    r1 = client.post(
        "/api/v1/interact",
        json={"query": "Donnes moi les ingrédients pour Orzo brocolis", "source": "session_test_1"},
    )
    assert r1.status_code == 200
    assert "Orzo brocolis" in r1.json()["spoken_response"]

    # 2. Deuxième requête en anaphore contextuelle : "Ajoutes ces ingrédients sauf les champignons"
    r2 = client.post(
        "/api/v1/interact",
        json={"query": "Ajoutes ces ingrédients sauf les champignons", "source": "session_test_1"},
    )
    assert r2.status_code == 200
    res_data = r2.json()
    assert res_data["intent"]["intent"] == "add_recipe_ingredients"
    assert "Orzo brocolis" in res_data["spoken_response"]
    assert "hors champignons" in res_data["spoken_response"]

    # Vérification que le connecteur a bien été appelé avec la recette mémorisée
    meals.add_recipe_ingredients_to_shopping_list.assert_called_with(
        recipe_name="Orzo brocolis",
        exclude_items=["champignons"],
    )


def test_interact_conversational_anaphora_without_context():
    """Vérifie le message d'aide poli si l'utilisateur utilise une anaphore sans contexte de recette préalable."""
    response = client.post(
        "/api/v1/interact",
        json={"query": "Ajoutes ces ingrédients", "source": "session_isolated_orphan"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["intent"]["intent"] == "add_recipe_ingredients"
    assert "Je ne sais pas de quelle recette vous parlez" in data["spoken_response"]


def test_interact_multi_turn_with_politeness_and_modal_anaphora(meals):
    """Vérifie l'enchaînement naturel : consultation -> politesse ('ok merci') -> anaphore modale ('tu peux tout rajouter')."""
    meals.get_recipe_ingredients.return_value = Recipe(
        name="Wrap de légumes",
        ingredients=["Wrap", "Salade", "Tomates cerises", "Carotte", "Crème fraiche"],
    )
    meals.add_recipe_ingredients_to_shopping_list.return_value = (
        Recipe(name="Wrap de légumes", ingredients=["Wrap", "Salade", "Tomates cerises", "Carotte", "Crème fraiche"]),
        [
            WaitingListItem(item="Wrap", rayon="Pain"),
            WaitingListItem(item="Salade", rayon="Légumes"),
            WaitingListItem(item="Tomates cerises", rayon="Légumes"),
            WaitingListItem(item="Carotte", rayon="Légumes"),
            WaitingListItem(item="Crème fraiche", rayon="Frais"),
        ],
    )

    # 1. Consultation des ingrédients
    r1 = client.post(
        "/api/v1/interact",
        json={"query": "Qu'est-ce qu'il faut pour faire du Wrap de légumes ?", "source": "session_wrap_test"},
    )
    assert r1.status_code == 200
    assert "Wrap de légumes" in r1.json()["spoken_response"]

    # 2. Politesse : 'ok merci'
    r2 = client.post(
        "/api/v1/interact",
        json={"query": "ok merci", "source": "session_wrap_test"},
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["intent"]["intent"] == "small_talk"
    assert any(w in d2["spoken_response"].lower() for w in ["plaisir", "prie", "service"])

    # 3. Anaphore modale : 'tu peux tout rajouter a la liste d'ingrédients'
    r3 = client.post(
        "/api/v1/interact",
        json={"query": "tu peux tout rajouter a la liste d'ingrédients", "source": "session_wrap_test"},
    )
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["intent"]["intent"] == "add_recipe_ingredients"
    assert "Wrap de légumes" in d3["spoken_response"]
    meals.add_recipe_ingredients_to_shopping_list.assert_called_with(
        recipe_name="Wrap de légumes",
        exclude_items=None,
    )


def test_interact_smart_next_meal_and_recipe_anaphora(meals):
    """'On mange quoi?' récupère le prochain repas réel et alimente l'anaphore d'ingrédients."""
    meals.get_next_meal_plan.return_value = (
        DayMealPlan(date_str="21/09/2026", day_name="Lundi", dinner="Salade de lentilles"),
        "dinner",
        "ce soir",
        "Salade de lentilles",
    )
    meals.get_recipe_ingredients.return_value = Recipe(
        name="Salade de lentilles",
        ingredients=["Lentilles", "Échalote", "Vinaigre", "Moutarde"],
    )

    # 1. On mange quoi?
    r1 = client.post(
        "/api/v1/interact",
        json={"query": "On mange quoi?", "source": "session_next_meal_test"},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert "Salade de lentilles" in d1["spoken_response"]
    assert "ce soir" in d1["spoken_response"]

    # 2. quel ingredients faut-il ?
    r2 = client.post(
        "/api/v1/interact",
        json={"query": "quel ingredients faut-il ?", "source": "session_next_meal_test"},
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["intent"]["intent"] == "get_recipe_ingredients"
    assert "Salade de lentilles" in d2["spoken_response"]
    assert "Lentilles" in d2["spoken_response"]
    meals.get_recipe_ingredients.assert_called_with("Salade de lentilles")


def test_interact_meal_plan_both_lunch_and_dinner(meals):
    """Vérifie l'affichage combiné midi et soir pour une requête de journée complète."""
    meals.get_meal_plan.return_value = DayMealPlan(
        date_str="24/09/2026",
        day_name="Jeudi",
        lunch="Salade César",
        dinner="Gratin dauphinois",
    )

    r = client.post(
        "/api/v1/interact",
        json={"query": "Qu'est ce qu'on mange Jeudi prochain ?", "source": "session_both_meals_test"},
    )
    assert r.status_code == 200
    spoken = r.json()["spoken_response"]
    assert "Salade César" in spoken
    assert "Gratin dauphinois" in spoken
    assert "midi" in spoken
    assert "soir" in spoken


def test_interact_set_meal_plan_unknown_recipe_confirmation_flow(meals):
    """Si la recette est inconnue, demande confirmation avant insertion (Oui / Non)."""
    # "poulet" n'est pas dans les recettes
    meals.get_recipe_ingredients.return_value = None
    meals.set_meal_plan.return_value = DayMealPlan(
        date_str="24/09/2026",
        day_name="Jeudi",
        dinner="Poulet rôti",
    )

    # 1. Demande de planification
    r1 = client.post(
        "/api/v1/interact",
        json={"query": "prévois du poulet pour jeudi", "source": "session_confirm_flow"},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert "pas répertoriée" in d1["spoken_response"]
    assert "Voulez-vous quand même" in d1["spoken_response"]
    meals.set_meal_plan.assert_not_called()

    # 2. Utilisateur confirme avec "oui"
    r2 = client.post(
        "/api/v1/interact",
        json={"query": "oui", "source": "session_confirm_flow"},
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert "confirmé" in d2["spoken_response"]
    meals.set_meal_plan.assert_called_once()


def test_interact_get_waiting_list_specifically(meals):
    """'donne moi la liste d'attente' filtre spécifiquement les articles en attente."""
    meals.get_shopping_list.return_value = {
        "waiting_list": [
            WaitingListItem(item="Café", rayon="Épicerie"),
            WaitingListItem(item="Blanc de poulet", rayon="Boucherie"),
        ],
        "current_week_items": [
            ShoppingItem(name="Pommes", checked=False),
        ],
    }

    r = client.post("/api/v1/interact", json={"query": "donne moi la liste d'attente"})
    assert r.status_code == 200
    spoken = r.json()["spoken_response"]
    assert "liste d'attente" in spoken
    assert "Café" in spoken
    assert "Blanc de poulet" in spoken
    assert "Pommes" not in spoken


def test_interact_what_to_buy_synonym(meals):
    """'Qu'est ce que je doit acheter ?' renvoie la liste de courses unifiée."""
    meals.get_shopping_list.return_value = {
        "waiting_list": [WaitingListItem(item="Crème fraiche", rayon="Frais")],
        "current_week_items": [ShoppingItem(name="Pain", checked=False)],
    }

    r = client.post("/api/v1/interact", json={"query": "Qu'est ce que je doit acheter ?"})
    assert r.status_code == 200
    spoken = r.json()["spoken_response"]
    assert "Crème fraiche" in spoken
    assert "Pain" in spoken


def test_interact_mark_all_shopping_bought(meals):
    """'J'ai acheté tout les produit de la listes d'attente' coche tous les articles."""
    meals.mark_shopping_items_bought.return_value = ["Café", "Blanc de poulet", "Crème fraiche"]

    r = client.post("/api/v1/interact", json={"query": "J'ai acheté tout les produit de la listes d'attente"})
    assert r.status_code == 200
    spoken = r.json()["spoken_response"]
    assert "tous les articles" in spoken
    assert "3" in spoken
    meals.mark_shopping_items_bought.assert_called_with(mark_all=True)


THIS_WEEK_AND_WAITING_LIST = {
    "waiting_list": [WaitingListItem(item="Chocolat", rayon="Petit dej + bio")],
    "current_week_items": [
        ShoppingItem(name="Bananes", checked=False, rayon="Fruits"),
        ShoppingItem(name="Pommes", checked=True, rayon="Fruits"),
        ShoppingItem(name="Lait", checked=False, rayon="Oeufs/farine/lait"),
    ],
}


@pytest.mark.parametrize("query, present, absent", [
    ('j\'ai quoi a acheter au rayon "Fruits"', ["Bananes", "coché"], ["Chocolat", "Lait"]),
    ("Il me reste quoi a acheté", ["Bananes", "Lait", "1 article(s) déjà coché"], ["Chocolat"]),
    ("qu'est-ce qui est déjà coché au rayon Fruits ?", ["Pommes"], ["Bananes"]),
])
def test_interact_shopping_questions_read_only_this_week(meals, query, present, absent):
    """Reste à acheter / déjà coché, par rayon ou non : « Cette semaine » seule, jamais la liste d'attente."""
    meals.get_shopping_list.return_value = THIS_WEEK_AND_WAITING_LIST

    r = client.post("/api/v1/interact", json={"query": query})
    assert r.status_code == 200
    spoken = r.json()["spoken_response"]
    assert [word for word in present if word not in spoken] == []
    assert [word for word in absent if word in spoken] == []


def test_interact_shopping_rayon_conversational_followup(meals):
    """Enchaînement conversationnel : 'au rayon Charcuterie' après une première question."""
    meals.get_shopping_list.return_value = {
        "waiting_list": [],
        "current_week_items": [
            ShoppingItem(name="Jambon", checked=False, rayon="Charcuterie"),
        ],
    }

    r = client.post(
        "/api/v1/interact",
        json={"query": "au rayon Charcuterie", "session_id": "test_session_rayon"},
    )
    assert r.status_code == 200
    spoken = r.json()["spoken_response"]
    assert "Charcuterie" in spoken
    assert "Jambon" in spoken


def test_interact_explicit_weekday_plus_date(meals):
    """'qu'est ce qu'on mange dimanche 20 septembre ?' interroge bien le 20/09/2026 et non le 27/09/2026."""
    meals.get_meal_plan.return_value = DayMealPlan(
        date_str="20/09/2026",
        day_name="Dimanche",
        lunch="Avocado toast",
        dinner="Gauffre carotte + Crudités",
    )

    r = client.post("/api/v1/interact", json={"query": "qu'est ce qu'on mange dimanche 20 septembre ?"})
    assert r.status_code == 200
    spoken = r.json()["spoken_response"]
    assert "20/09/2026" in spoken
    assert "27/09/2026" not in spoken
    assert "Avocado toast" in spoken
    assert "Gauffre carotte" in spoken






