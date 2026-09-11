"""Tests unitaires (TDD) pour le connecteur MealsShoppingConnector."""
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock
import pytest

from app.connectors.sheets.models import (
    DayMealPlan,
    Recipe,
    WaitingListItem,
    ShoppingItem,
)
from app.connectors.sheets.meals_connector import (
    MealsShoppingConnector,
    RecipeNotFoundError,
    DayMealPlanNotFoundError,
)


def create_mock_worksheet(title: str, records: list[list]) -> MagicMock:
    """Helper pour créer un mock de feuille gspread."""
    ws = MagicMock()
    ws.title = title
    ws.get_all_values.return_value = records
    ws.row_values.side_effect = lambda idx: records[idx - 1] if 0 < idx <= len(records) else []
    return ws


@pytest.fixture
def mock_spreadsheet():
    """Crée un classeur mocké avec toutes les données nécessaires."""
    today = date.today()
    today_str = today.strftime("%d/%m/%Y")
    tomorrow = today + timedelta(days=1)
    tomorrow_str = tomorrow.strftime("%d/%m/%Y")

    repas_2026_data = [
        ["Date", "Jour", "Midi", "Soir", "Notes / Magasin"],
        [today_str, "Vendredi", "Salade composée", "Pizza maison", "Supermarché"],
        [tomorrow_str, "Samedi", "Pâtes pesto", "Burger veggie", ""],
    ]

    recettes_data = [
        ["Plat", "Catégorie", "Catégorie 2", "Complet", "Ingrédient", "", "", ""],
        ["Risotto de quinoa", "Féculents", "Chaud", "TRUE", "Quinoa", "Champignons", "Bouillon", "Parmesan"],
        ["Pizza maison", "Plaisir", "Four", "TRUE", "Pâte à pizza", "Sauce tomate", "Mozzarella", ""],
        ["Panini", "Sandwich", "Chaud", "FALSE", "Pain panini", "Jambon", "Fromage croque", ""],
        ["Boeuf aux poivrons", "Plat", "Chaud", "FALSE", "Chair à saucisse", "Poivrons", "Pomme de terre", "Féta", "oignon", "Ail", "Pulpe de tomates"],
    ]

    recette_festive_data = [
        ["Plat", "Catégorie", "Catégorie 2", "Complet", "Ingrédient", "", ""],
        ["Guacamole", "Apéro", "Froid", "FALSE", "Avocat", "Épices guacamole", "Citron vert"],
    ]

    ingredients_rayons_data = [
        ["Ingrédient", "Rayon"],
        ["Quinoa", "Féculents"],
        ["Champignons", "Légumes"],
        ["Bouillon", "Épicerie"],
        ["Parmesan", "Fromage"],
        ["Café bio", "Épicerie"],
        ["Avocat", "Légumes"],
        ["Citron vert", "Fruits"],
        ["Jambon", "Charcuterie"],
        ["Pain panini", "Boulangerie"],
        ["Fromage croque", "Fromage"],
    ]

    hors_repas_data = [
        ["Nom", "pré-cocher?", "rayon"],
        ["Papier sulfurisé", "FALSE", "Entretien"],
        ["Dentifrice", "FALSE", "Hygiène"],
    ]

    liste_attente_data = [
        ["Acheté", "Article", "Date d'ajout"],
        ["FALSE", "Café bio", "10/09/2026"],
        ["TRUE", "Dentifrice", "09/09/2026"],
    ]

    cette_semaine_data = [
        ["", "", "Midi", "", "Soir", "", "", ""],
        ["sam. 05", "", "Rouleau de printemps", "", "Patates au four", "", "", ""],
        ["", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", ""],
        ["Fruits", "", "Légumes", "", "Épicerie", "", "Entretien", ""],
        ["FALSE", "Pommes", "FALSE", "Carottes", "TRUE", "Riz", "FALSE", "Éponge"],
    ]

    ws_map = {
        f"repas {today.year}": create_mock_worksheet(f"repas {today.year}", repas_2026_data),
        "Recettes": create_mock_worksheet("Recettes", recettes_data),
        "Recette festive": create_mock_worksheet("Recette festive", recette_festive_data),
        "Ingredients_Rayons": create_mock_worksheet("Ingredients_Rayons", ingredients_rayons_data),
        "Hors_Repas": create_mock_worksheet("Hors_Repas", hors_repas_data),
        "Liste_Attente": create_mock_worksheet("Liste_Attente", liste_attente_data),
        "Cette semaine": create_mock_worksheet("Cette semaine", cette_semaine_data),
        "Rayons": create_mock_worksheet("Rayons", [["Rayons", "Ordre"], ["Légumes", "1"]]),
        "Courses festives": create_mock_worksheet("Courses festives", [["Fruits", "", "Légumes"]]),
    }

    sh = MagicMock()
    sh.worksheets.return_value = list(ws_map.values())
    sh.worksheet.side_effect = lambda name: ws_map[name] if name in ws_map else (_ for _ in ()).throw(Exception(f"Worksheet {name} not found"))
    return sh


def test_get_meal_plan_today(mock_spreadsheet):
    """Vérifie la récupération du repas pour aujourd'hui (soir par défaut)."""
    connector = MealsShoppingConnector(spreadsheet=mock_spreadsheet)
    plan = connector.get_meal_plan(period="soir")

    assert isinstance(plan, DayMealPlan)
    assert plan.dinner == "Pizza maison"
    assert plan.lunch == "Salade composée"


def test_get_meal_plan_tomorrow(mock_spreadsheet):
    """Vérifie la récupération du repas pour demain."""
    connector = MealsShoppingConnector(spreadsheet=mock_spreadsheet)
    plan = connector.get_meal_plan(period="demain")

    assert isinstance(plan, DayMealPlan)
    assert plan.dinner == "Burger veggie"
    assert plan.lunch == "Pâtes pesto"


def test_get_meal_plan_not_found(mock_spreadsheet):
    """Vérifie qu'une date inexistante lève DayMealPlanNotFoundError."""
    connector = MealsShoppingConnector(spreadsheet=mock_spreadsheet)
    with pytest.raises(DayMealPlanNotFoundError):
        connector.get_meal_plan(target_date="31/12/2099")


def test_get_recipe_ingredients_standard(mock_spreadsheet):
    """Vérifie la recherche d'ingrédients d'une recette classique (Recettes)."""
    connector = MealsShoppingConnector(spreadsheet=mock_spreadsheet)
    recipe = connector.get_recipe_ingredients("risotto de quinoa")

    assert recipe is not None
    assert recipe.name == "Risotto de quinoa"
    assert "Quinoa" in recipe.ingredients
    assert "Champignons" in recipe.ingredients
    assert "Parmesan" in recipe.ingredients
    assert recipe.source_sheet == "Recettes"


def test_get_recipe_ingredients_festive(mock_spreadsheet):
    """Vérifie la recherche d'ingrédients dans l'onglet Recette festive."""
    connector = MealsShoppingConnector(spreadsheet=mock_spreadsheet)
    recipe = connector.get_recipe_ingredients("Guacamole")

    assert recipe is not None
    assert recipe.name == "Guacamole"
    assert recipe.is_festive is True
    assert "Avocat" in recipe.ingredients
    assert "Citron vert" in recipe.ingredients


def test_get_recipe_ingredients_not_found(mock_spreadsheet):
    """Vérifie le retour None si la recette est introuvable."""
    connector = MealsShoppingConnector(spreadsheet=mock_spreadsheet)
    recipe = connector.get_recipe_ingredients("Plat imaginaire 404")
    assert recipe is None


def test_set_meal_plan_success(mock_spreadsheet):
    """Vérifie la modification d'un repas dans le planning annuel."""
    connector = MealsShoppingConnector(spreadsheet=mock_spreadsheet)
    today = date.today()

    updated_plan = connector.set_meal_plan(
        meal="Lasagnes végétariennes",
        target_date=today,
        meal_type="soir",
    )

    assert updated_plan.dinner == "Lasagnes végétariennes"
    # Vérifie qu'un appel d'écriture a bien eu lieu sur la cellule Soir (colonne 4)
    ws = mock_spreadsheet.worksheet(f"repas {today.year}")
    ws.update_cell.assert_called_once()


def test_add_shopping_item_known_rayon(mock_spreadsheet):
    """Vérifie l'ajout d'un article dans Liste_Attente avec rayon résolu."""
    connector = MealsShoppingConnector(spreadsheet=mock_spreadsheet)
    item, warning = connector.add_shopping_item("Champignons")

    assert isinstance(item, WaitingListItem)
    assert item.item == "Champignons"
    assert item.rayon == "Légumes"
    assert item.is_bought is False
    assert warning is None

    # Vérifie l'insertion de ligne dans Liste_Attente
    ws = mock_spreadsheet.worksheet("Liste_Attente")
    ws.append_row.assert_called_once()


def test_add_shopping_item_unknown_rayon_warning(mock_spreadsheet):
    """Vérifie l'attribution du rayon Divers et émission d'un warning si inconnu."""
    connector = MealsShoppingConnector(spreadsheet=mock_spreadsheet)
    item, warning = connector.add_shopping_item("Ampoule LED")

    assert item.rayon == "Divers"
    assert warning is not None
    assert "Ampoule LED" in warning


def test_add_recipe_ingredients_to_shopping_list_all(mock_spreadsheet):
    """Vérifie l'ajout de tous les ingrédients d'une recette dans la liste d'attente."""
    connector = MealsShoppingConnector(spreadsheet=mock_spreadsheet)
    recipe, added_items = connector.add_recipe_ingredients_to_shopping_list("Guacamole")

    assert recipe.name == "Guacamole"
    assert len(added_items) == 3
    item_names = [it.item for it in added_items]
    assert "Avocat" in item_names
    assert "Citron vert" in item_names


def test_add_recipe_ingredients_with_exclude(mock_spreadsheet):
    """Vérifie l'ajout des ingrédients en excluant ceux déjà possédés."""
    connector = MealsShoppingConnector(spreadsheet=mock_spreadsheet)
    recipe, added_items = connector.add_recipe_ingredients_to_shopping_list(
        "Guacamole",
        exclude_items=["Citron vert"],
    )

    item_names = [it.item for it in added_items]
    assert "Avocat" in item_names
    assert "Citron vert" not in item_names
    assert len(added_items) == 2


def test_add_shopping_item_cleans_determinants(mock_spreadsheet):
    """Vérifie que l'ajout d'un article nettoie les déterminants (du, le, de la...)."""
    connector = MealsShoppingConnector(spreadsheet=mock_spreadsheet)
    item, warning = connector.add_shopping_item("du café bio")

    assert item.item == "Café bio"
    assert item.rayon == "Épicerie"
    assert warning is None


def test_add_recipe_ingredients_with_exclude_with_determinants(mock_spreadsheet):
    """Vérifie l'exclusion même si l'utilisateur spécifie un déterminant (sauf le jambon)."""
    connector = MealsShoppingConnector(spreadsheet=mock_spreadsheet)
    recipe, added_items = connector.add_recipe_ingredients_to_shopping_list(
        "Panini",
        exclude_items=["le jambon"],
    )

    item_names = [it.item for it in added_items]
    assert "Pain panini" in item_names
    assert "Fromage croque" in item_names
    assert "Jambon" not in item_names
    assert len(added_items) == 2


def test_add_recipe_ingredients_with_multiple_exclusions(mock_spreadsheet):
    """Vérifie le support des exclusions multiples séparées par 'et'."""
    connector = MealsShoppingConnector(spreadsheet=mock_spreadsheet)
    recipe, added_items = connector.add_recipe_ingredients_to_shopping_list(
        "Panini",
        exclude_items=["le jambon et le fromage croque"],
    )

    item_names = [it.item for it in added_items]
    assert "Pain panini" in item_names
    assert "Jambon" not in item_names
    assert "Fromage croque" not in item_names
    assert len(added_items) == 1


def test_add_recipe_ingredients_with_plural_and_conjunction_exclusion(mock_spreadsheet):
    """Vérifie l'exclusion avec pluriel et conjonction (sauf ail et oignons)."""
    connector = MealsShoppingConnector(spreadsheet=mock_spreadsheet)
    recipe, added_items = connector.add_recipe_ingredients_to_shopping_list(
        "Boeuf aux poivrons",
        exclude_items=["ail et oignons"],
    )

    item_names = [it.item for it in added_items]
    assert "Ail" not in item_names
    assert "oignon" not in item_names
    # La recette contenait 7 ingrédients, 2 sont exclus -> 5 doivent être ajoutés
    assert len(added_items) == 5




def test_get_shopping_list_unified(mock_spreadsheet):
    """Vérifie la synthèse des articles non achetés (Liste_Attente + Cette semaine)."""
    connector = MealsShoppingConnector(spreadsheet=mock_spreadsheet)
    shopping_summary = connector.get_shopping_list()

    assert "waiting_list" in shopping_summary
    assert "current_week_items" in shopping_summary
    # Dans le mock, seul 'Café bio' a Acheté=FALSE dans Liste_Attente
    assert len(shopping_summary["waiting_list"]) == 1
    assert shopping_summary["waiting_list"][0].item == "Café bio"


def test_mark_shopping_items_bought(mock_spreadsheet):
    """Vérifie le marquage comme acheté dans Liste_Attente."""
    connector = MealsShoppingConnector(spreadsheet=mock_spreadsheet)
    marked = connector.mark_shopping_items_bought(["Café bio"])

    assert "Café bio" in marked
    ws = mock_spreadsheet.worksheet("Liste_Attente")
    ws.update_cell.assert_called()


def test_clear_shopping_list_only_bought(mock_spreadsheet):
    """Vérifie la suppression des articles achetés uniquement."""
    connector = MealsShoppingConnector(spreadsheet=mock_spreadsheet)
    deleted_count = connector.clear_shopping_list(only_bought=True)

    assert deleted_count == 1  # Dans le mock, seul Dentifrice a Acheté=TRUE
    ws = mock_spreadsheet.worksheet("Liste_Attente")
    ws.delete_rows.assert_called()
