"""Tests fonctionnels de l'endpoint d'interaction universel."""
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from app.main import app, set_meals_connector
from app.connectors.sheets.models import (
    DayMealPlan,
    Recipe,
    WaitingListItem,
    ShoppingItem,
)

client = TestClient(app)


def test_interact_meal_plan_fallback():
    """Sans connecteur injecté, l'endpoint répond avec le fallback gracieux."""
    set_meals_connector(None)
    response = client.post("/api/v1/interact", json={"query": "Qu'est-ce qu'on mange ce soir ?"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "repas" in data["spoken_response"].lower() or "lasagnes" in data["spoken_response"].lower()
    assert data["intent"]["intent"] == "get_meal_plan"


def test_interact_with_mocked_connector():
    """Avec connecteur injecté, l'endpoint appelle les méthodes métier et renvoie la réponse adaptée."""
    mock_connector = MagicMock()
    mock_connector.get_meal_plan.return_value = DayMealPlan(
        date_str="11/09/2026",
        day_name="Vendredi",
        lunch="Salade César",
        dinner="Pizza 4 fromages",
    )
    mock_connector.get_recipe_ingredients.return_value = Recipe(
        name="Risotto de quinoa",
        category="Féculents",
        is_complete=True,
        ingredients=["Quinoa", "Champignons", "Parmesan"],
    )
    mock_connector.add_recipe_ingredients_to_shopping_list.return_value = (
        Recipe(name="Guacamole", ingredients=["Avocat", "Épices"]),
        [
            WaitingListItem(item="Avocat", rayon="Légumes"),
            WaitingListItem(item="Épices", rayon="Épicerie"),
        ],
    )
    mock_connector.set_meal_plan.return_value = DayMealPlan(
        date_str="11/09/2026",
        day_name="Vendredi",
        dinner="Pâtes carbonara",
    )
    mock_connector.add_shopping_item.return_value = (
        WaitingListItem(item="Café bio", rayon="Épicerie"),
        None,
    )
    mock_connector.get_shopping_list.return_value = {
        "waiting_list": [WaitingListItem(item="Café bio", rayon="Épicerie")],
        "current_week_items": [ShoppingItem(name="Pommes", checked=False)],
    }
    mock_connector.mark_shopping_items_bought.return_value = ["Café bio"]
    mock_connector.clear_shopping_list.return_value = 1

    set_meals_connector(mock_connector)

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
    set_meals_connector(None)


def test_interact_budget_query():
    response = client.post(
        "/api/v1/interact",
        json={"query": "Combien il reste de budget courses ?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "budget courses" in data["spoken_response"]


def test_interact_conversational_anaphora_followup():
    """Vérifie le chaînage conversationnel : consultation de recette puis 'Ajoutes ces ingrédients'."""
    mock_connector = MagicMock()
    mock_connector.get_recipe_ingredients.return_value = Recipe(
        name="Orzo brocolis",
        ingredients=["Orzo", "Brocolis", "Champignons", "Poitrine", "Lait"],
    )
    mock_connector.add_recipe_ingredients_to_shopping_list.return_value = (
        Recipe(name="Orzo brocolis", ingredients=["Orzo", "Brocolis", "Champignons", "Poitrine", "Lait"]),
        [
            WaitingListItem(item="Orzo", rayon="Féculents"),
            WaitingListItem(item="Brocolis", rayon="Légumes"),
            WaitingListItem(item="Poitrine", rayon="Boucherie"),
            WaitingListItem(item="Lait", rayon="Frais"),
        ],
    )
    set_meals_connector(mock_connector)

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
    mock_connector.add_recipe_ingredients_to_shopping_list.assert_called_with(
        recipe_name="Orzo brocolis",
        exclude_items=["champignons"],
    )

    set_meals_connector(None)


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


def test_interact_multi_turn_with_politeness_and_modal_anaphora():
    """Vérifie l'enchaînement naturel : consultation -> politesse ('ok merci') -> anaphore modale ('tu peux tout rajouter')."""
    mock_connector = MagicMock()
    mock_connector.get_recipe_ingredients.return_value = Recipe(
        name="Wrap de légumes",
        ingredients=["Wrap", "Salade", "Tomates cerises", "Carotte", "Crème fraiche"],
    )
    mock_connector.add_recipe_ingredients_to_shopping_list.return_value = (
        Recipe(name="Wrap de légumes", ingredients=["Wrap", "Salade", "Tomates cerises", "Carotte", "Crème fraiche"]),
        [
            WaitingListItem(item="Wrap", rayon="Pain"),
            WaitingListItem(item="Salade", rayon="Légumes"),
            WaitingListItem(item="Tomates cerises", rayon="Légumes"),
            WaitingListItem(item="Carotte", rayon="Légumes"),
            WaitingListItem(item="Crème fraiche", rayon="Frais"),
        ],
    )
    set_meals_connector(mock_connector)

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
    mock_connector.add_recipe_ingredients_to_shopping_list.assert_called_with(
        recipe_name="Wrap de légumes",
        exclude_items=None,
    )

    set_meals_connector(None)




