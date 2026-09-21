"""Tests unitaires des modèles Pydantic pour Google Sheets."""
from datetime import date
from app.connectors.sheets.models import (
    DayMealPlan,
    Recipe,
    ShoppingItem,
    RayonSetting,
    WaitingListItem,
    SheetSchemaSnapshot,
)


def test_waiting_list_item_model():
    item = WaitingListItem(
        item="Papier sulfurisé",
        is_bought=False,
        added_at="11/09/2026",
        rayon="Entretien",
    )
    assert item.item == "Papier sulfurisé"
    assert item.is_bought is False
    assert item.added_at == "11/09/2026"
    assert item.rayon == "Entretien"


def test_day_meal_plan_parsing():
    plan = DayMealPlan(
        date_str="03/01/2026",
        day_name="Samedi",
        lunch="cake + salade d'endive",
        dinner="wrap de légumes",
        notes="",
    )
    assert plan.parse_date() == date(2026, 1, 3)
    assert plan.lunch == "cake + salade d'endive"
    assert plan.dinner == "wrap de légumes"
    assert plan.notes is None  # empty string convertie en None


def test_recipe_model():
    recipe = Recipe(
        name="Riz cantonnais",
        category="Féculents",
        is_complete=True,
        ingredients=["Riz", "Oeufs", "Jambon", "Petit pois"],
    )
    assert recipe.name == "Riz cantonnais"
    assert len(recipe.ingredients) == 4
    assert recipe.is_complete is True


def test_shopping_item_model():
    item = ShoppingItem(name="Avocat x4", checked=False, rayon="Légumes")
    assert item.name == "Avocat x4"
    assert item.rayon == "Légumes"
    assert item.checked is False


def test_festive_recipe_model():
    recipe = Recipe(
        name="guacamole",
        category="Apéro",
        is_festive=True,
        source_sheet="Recette festive",
        ingredients=["Avocat", "Epice guacamole"],
    )
    assert recipe.name == "guacamole"
    assert recipe.category == "Apéro"
    assert recipe.is_festive is True
    assert recipe.source_sheet == "Recette festive"
    assert len(recipe.ingredients) == 2


def test_sheet_schema_snapshot_defaults():
    snapshot = SheetSchemaSnapshot()
    assert "Date" in snapshot.planning_headers
    assert "Jour" in snapshot.planning_headers
    assert "Midi" in snapshot.planning_headers
    assert "Soir" in snapshot.planning_headers
    assert "Recettes" in snapshot.required_worksheets
    assert "Recette festive" in snapshot.required_worksheets
    assert "Cette semaine" in snapshot.required_worksheets
    assert "Courses festives" in snapshot.required_worksheets
    assert "Rayons" in snapshot.required_worksheets
    assert "Hors_Repas" in snapshot.required_worksheets
    assert "Ingredients_Rayons" in snapshot.required_worksheets
    assert "Liste_Attente" in snapshot.required_worksheets
    assert "Acheté" in snapshot.liste_attente_headers
    assert "Article" in snapshot.liste_attente_headers
