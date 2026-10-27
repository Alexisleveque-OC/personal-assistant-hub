"""Outils agent Repas & Courses (Phase 6.8 - Étape 5) : lecture, mutations via le connecteur et instantanés d'annulation."""
from datetime import date, timedelta

import pytest

from app.connectors.sheets.meals_connector import MealsShoppingConnector
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.tool_registry import ToolRegistry
from app.core.agent.tools.sport_tools import SportTools
from app.core.agent.undo import UndoJournal, UndoService
from app.core.agent.tools.meals_models import MealUndo, RayonLearnedUndo, ShoppingAddedUndo, ShoppingCheckedUndo, ShoppingRemovedUndo
from app.core.agent.tools.meals_registry import meals_tool_definitions
from app.core.agent.tools.meals_tools import MealsTools
from tests.meals_fakes import (
    MealsSheetState,
    WeekItem,
    build_meals_spreadsheet,
    planned_meals,
    waiting_rows,
    week_rows,
)

TODAY = date(2026, 10, 21)  # mercredi
TOMORROW = TODAY + timedelta(days=1)


@pytest.fixture
def sheet():
    return build_meals_spreadsheet(MealsSheetState(
        today=TODAY,
        waiting=[("Lait", True), ("Pain", False)],
        week=[WeekItem("Quinoa", "Épicerie", checked=True), WeekItem("Courgette", "Fruits & Légumes")],
        meals={TODAY: ("Salade composée", "Risotto de quinoa"), TOMORROW: ("", "Gratin de courgettes")},
    ))


@pytest.fixture
def connector(sheet):
    return MealsShoppingConnector(spreadsheet=sheet)


@pytest.fixture
def tools(connector):
    return MealsTools(connector)


@pytest.fixture
def registry(tools):
    return ToolRegistry(meals_tool_definitions(tools))


async def _call(registry, name, **args):
    return await registry.execute(name, args)


# --- Liste de courses --------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_shopping_list_shows_items_left_to_buy_with_list_and_rayon(registry):
    execution = await _call(registry, "get_shopping_list")

    assert execution.error is None
    assert execution.response["articles"] == [
        {"nom": "Pain", "rayon": "Épicerie", "liste": "attente", "coche": False},
        {"nom": "Courgette", "rayon": "Fruits & Légumes", "liste": "semaine", "coche": False},
    ]


@pytest.mark.asyncio
async def test_shopping_list_can_include_checked_items_and_filter_by_rayon(registry):
    execution = await _call(registry, "get_shopping_list", rayon="epicerie", inclure_coches=True)

    assert [(a["nom"], a["coche"]) for a in execution.response["articles"]] == [("Pain", False), ("Quinoa", True)]


@pytest.mark.asyncio
async def test_add_items_resolves_known_rayons_and_validates_explicit_ones(registry, sheet, connector):
    execution = await _call(registry, "add_shopping_items", articles=[{"nom": "du beurre"}, {"nom": "lessive", "rayon": "hygiène"}])

    assert execution.error is None
    assert execution.response["ajoutes"] == [
        {"nom": "Beurre", "rayon": "Frais", "liste": "attente", "coche": False},
        {"nom": "Lessive", "rayon": "Hygiène", "liste": "attente", "coche": False},
    ]
    assert execution.response["rayon_a_demander"] == []
    assert waiting_rows(sheet)[-2:] == [("Beurre", False), ("Lessive", False)]
    assert execution.undos == [ShoppingAddedUndo(items=["Beurre", "Lessive"])]
    # Écriture → cache invalidé ou mis à jour : la lecture suivante voit les ajouts.
    assert {"Beurre", "Lessive"} <= {it.item for it in connector.get_shopping_list()["waiting_list"]}


@pytest.mark.asyncio
async def test_unknown_article_is_not_added_and_left_for_the_app_to_ask(registry, tools, sheet):
    execution = await _call(registry, "add_shopping_items", articles=[{"nom": "lait"}, {"nom": "papier cadeau"}])

    assert [a["nom"] for a in execution.response["ajoutes"]] == ["Lait"]
    assert execution.response["rayon_a_demander"] == ["papier cadeau"]
    assert "rayons_disponibles" not in execution.response  # le modèle ne choisit plus le rayon
    assert ("Papier cadeau", False) not in waiting_rows(sheet)
    assert tools.unknown_articles == ["papier cadeau"]


@pytest.mark.asyncio
async def test_rayon_chosen_by_the_model_for_an_unknown_article_is_ignored(registry, tools, sheet):
    execution = await _call(registry, "add_shopping_items", articles=[{"nom": "papier cadeau", "rayon": "Entretien"}])

    assert execution.response["ajoutes"] == []
    assert execution.response["rayon_a_demander"] == ["papier cadeau"]
    assert ("Papier cadeau", False) not in waiting_rows(sheet)


@pytest.mark.asyncio
async def test_rayon_said_by_the_user_for_an_unknown_article_is_saved(connector, sheet):
    tools = MealsTools(connector, user_words="Ajoute du papier cadeau au rayon entretien")
    registry = ToolRegistry(meals_tool_definitions(tools))

    execution = await _call(registry, "add_shopping_items", articles=[{"nom": "papier cadeau", "rayon": "Entretien"}])

    assert execution.response["ajoutes"] == [{"nom": "Papier cadeau", "rayon": "Entretien", "liste": "attente", "coche": False}]
    assert sheet.worksheet("Ingredients_Rayons").get_all_values()[-1] == ["Papier cadeau", "Entretien"]
    assert execution.undos == [
        RayonLearnedUndo(ingredient="Papier cadeau", rayon="Entretien"), ShoppingAddedUndo(items=["Papier cadeau"]),
    ]
    assert tools.unknown_articles == []


@pytest.mark.asyncio
async def test_invalid_explicit_rayon_is_rejected_before_any_write(registry, sheet):
    before = waiting_rows(sheet)

    execution = await _call(registry, "add_shopping_items", articles=[{"nom": "lait"}, {"nom": "piles", "rayon": "Bricolage"}])

    assert "Bricolage" in execution.error and "Entretien" in execution.error
    assert waiting_rows(sheet) == before
    assert execution.undos == []


@pytest.mark.asyncio
async def test_check_items_in_both_lists_and_reports_already_checked_or_unknown(registry, sheet):
    execution = await _call(registry, "check_shopping_items", noms=["le pain", "courgettes", "lait", "chocolat"])

    assert execution.response == {
        "modifies": ["Pain", "Courgette"], "deja_dans_cet_etat": ["lait"], "introuvables": ["chocolat"], "coche": True,
    }
    assert ("Pain", True) in waiting_rows(sheet)
    assert week_rows(sheet) == [("Quinoa", True), ("Courgette", True)]
    assert execution.undos == [ShoppingCheckedUndo(checked=True, waiting=["Pain"], week=["Courgette"])]


@pytest.mark.asyncio
async def test_uncheck_items(registry, sheet):
    execution = await _call(registry, "check_shopping_items", noms=["lait", "quinoa"], coche=False)

    assert execution.response["modifies"] == ["Lait", "Quinoa"]
    assert ("Lait", False) in waiting_rows(sheet)
    assert ("Quinoa", False) in week_rows(sheet)


@pytest.mark.asyncio
async def test_remove_items_only_from_the_waiting_list(registry, sheet):
    execution = await _call(registry, "remove_shopping_items", noms=["pain", "courgette", "chocolat"])

    assert execution.response["retires"] == ["Pain"]
    assert execution.response["introuvables"] == ["courgette", "chocolat"]
    assert "semaine" in execution.response["remarque"]
    assert waiting_rows(sheet) == [("Lait", True)]
    assert execution.undos == [ShoppingRemovedUndo(items=[{"item": "Pain", "is_bought": False, "added_at": "21/10/2026"}])]


@pytest.mark.asyncio
async def test_clear_removes_only_bought_waiting_items(registry, sheet):
    execution = await _call(registry, "clear_bought_shopping_items")

    assert execution.response["retires"] == ["Lait"]
    assert waiting_rows(sheet) == [("Pain", False)]
    assert week_rows(sheet) == [("Quinoa", True), ("Courgette", False)]
    assert len(execution.undos) == 1


# --- Repas & recettes -------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_meal_plan_over_a_date_range(registry):
    execution = await _call(registry, "get_meal_plan", date_debut=TODAY.isoformat(), date_fin=TOMORROW.isoformat())

    assert execution.response["jours"] == [
        {"date": "2026-10-21", "jour": "mercredi", "midi": "Salade composée", "soir": "Risotto de quinoa"},
        {"date": "2026-10-22", "jour": "jeudi", "midi": None, "soir": "Gratin de courgettes"},
    ]


@pytest.mark.asyncio
async def test_meal_plan_range_is_bounded(registry):
    execution = await _call(registry, "get_meal_plan", date_debut=TODAY.isoformat(), date_fin=(TODAY + timedelta(days=20)).isoformat())
    assert "14 jours" in execution.error


@pytest.mark.asyncio
async def test_meal_plan_missing_days_are_reported_not_hidden(registry):
    far = TODAY + timedelta(days=60)  # hors de l'onglet de la doublure
    execution = await _call(registry, "get_meal_plan", date_debut=far.isoformat())

    assert execution.response["jours"] == []
    assert execution.response["absents"] == [far.isoformat()]


@pytest.mark.asyncio
async def test_set_meal_uses_the_recipe_book_name_and_records_the_previous_dish(registry, sheet):
    execution = await _call(registry, "set_meal", date=TOMORROW.isoformat(), moment="soir", plat="chili")

    assert execution.error is None
    assert execution.response["jour"]["soir"] == "Chili sin carne"
    assert execution.response["precedent"] == "Gratin de courgettes"
    assert planned_meals(sheet)["22/10/2026"] == ("", "Chili sin carne")
    assert execution.undos == [MealUndo(date=TOMORROW, moment="soir", before="Gratin de courgettes", after="Chili sin carne")]


@pytest.mark.asyncio
async def test_set_meal_outside_the_recipe_book_requires_confirmation_in_a_later_turn(connector, sheet):
    first_turn = MealsTools(connector)
    registry = ToolRegistry(meals_tool_definitions(first_turn))
    refused = await _call(registry, "set_meal", date=TOMORROW.isoformat(), moment="midi", plat="Raclette")
    # Le modèle ne peut pas se confirmer lui-même dans le tour où la question n'a pas encore été posée.
    self_confirmed = await _call(registry, "set_meal", date=TOMORROW.isoformat(), moment="midi", plat="Raclette", hors_carnet_confirme=True)
    assert "confirm" in refused.error and "confirm" in self_confirmed.error
    assert planned_meals(sheet)["22/10/2026"] == ("", "Gratin de courgettes")
    assert first_turn.refused_dishes == ["Raclette"]

    next_turn = ToolRegistry(meals_tool_definitions(MealsTools(connector, confirmable_dishes=first_turn.refused_dishes)))
    confirmed = await _call(next_turn, "set_meal", date=TOMORROW.isoformat(), moment="midi", plat="raclette", hors_carnet_confirme=True)
    assert confirmed.error is None
    assert planned_meals(sheet)["22/10/2026"] == ("raclette", "Gratin de courgettes")


@pytest.mark.asyncio
async def test_recipe_ingredients(registry):
    found = await _call(registry, "get_recipe", nom="risotto quinoa")
    missing = await _call(registry, "get_recipe", nom="blanquette")

    assert found.response == {"nom": "Risotto de quinoa", "ingredients": ["Quinoa", "Courgette", "Bouillon", "Parmesan"]}
    assert "blanquette" in missing.error


@pytest.mark.asyncio
async def test_tools_fail_explicitly_without_a_meals_connector():
    registry = ToolRegistry(meals_tool_definitions(MealsTools(None)))

    execution = await _call(registry, "get_shopping_list")

    assert "indisponible" in execution.error


# --- Annulation ---------------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_whole_turn_of_chained_mutations_is_undone_exactly(registry, tools, sheet, isolate_sqlite_database):
    db = isolate_sqlite_database
    initial_waiting, initial_week, initial_meals = waiting_rows(sheet), week_rows(sheet), planned_meals(sheet)
    executions = [
        await _call(registry, "add_shopping_items", articles=[{"nom": "beurre"}]),
        await _call(registry, "check_shopping_items", noms=["pain", "courgette"]),
        await _call(registry, "remove_shopping_items", noms=["pain"]),  # même article, mutation suivante
        await _call(registry, "clear_bought_shopping_items"),
        await _call(registry, "set_meal", date=TOMORROW.isoformat(), moment="soir", plat="Lasagnes"),
    ]
    journal = UndoJournal(db)
    journal.record("meals-undo", [undo for e in executions for undo in e.undos])
    service = UndoService(SportTools(SqlSportConnector(db_manager=db)), db, journal, meals_tools=tools)

    outcome = service.undo_last("meals-undo")

    assert waiting_rows(sheet) == initial_waiting
    assert week_rows(sheet) == initial_week
    assert planned_meals(sheet) == initial_meals
    assert any("Gratin de courgettes" in label for label in outcome.restored)
    assert outcome.sport_session_ids == []


def test_undo_is_refused_when_the_meal_was_changed_since(tools, sheet, connector):
    undo = MealUndo(date=TOMORROW, moment="soir", before="Gratin de courgettes", after="Lasagnes")
    connector.set_meal_plan(meal="Pizza", target_date=TOMORROW, meal_type="soir")

    with pytest.raises(Exception, match="modifié depuis"):
        tools.check_undo(undo)


def test_undo_of_an_add_is_refused_when_the_item_is_already_gone(tools):
    with pytest.raises(Exception, match="Beurre"):
        tools.check_undo(ShoppingAddedUndo(items=["Beurre"]))
