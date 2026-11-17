"""Repas (retours du 17/11) : compléter un plat (« Quiche lorraine » + « coleslaw » → « Quiche lorraine + Coleslaw »)
et retirer un plat, à la voix comme depuis la feuille Repas. Annulables par le journal d'Otis.

Le séparateur « + » est celui du classeur : il permet de générer la liste de courses de chaque plat."""
from datetime import date, timedelta

import pytest

from app.connectors.sheets.meals_connector import MealsShoppingConnector
from app.core.agent.tool_registry import ToolRegistry
from app.core.agent.tools.meals_models import MealUndo
from app.core.agent.tools.meals_registry import meals_tool_definitions
from app.core.agent.tools.meals_tools import MealsTools
from tests.meals_fakes import MealsSheetState, build_meals_spreadsheet, planned_meals

TODAY = date(2026, 10, 21)  # mercredi
TOMORROW = TODAY + timedelta(days=1)


@pytest.fixture
def sheet():
    return build_meals_spreadsheet(MealsSheetState(
        today=TODAY,
        meals={TODAY: ("Salade composée", "Risotto de quinoa"), TOMORROW: ("", "Gratin de courgettes")},
    ))


@pytest.fixture
def connector(sheet):
    return MealsShoppingConnector(spreadsheet=sheet)


@pytest.fixture
def registry(connector):
    return ToolRegistry(meals_tool_definitions(MealsTools(connector)))


async def _call(registry, name, **args):
    return await registry.execute(name, args)


@pytest.mark.asyncio
async def test_add_mode_combines_with_the_planned_dish_using_the_recipe_book_name(registry, sheet):
    execution = await _call(registry, "set_meal", date=TOMORROW.isoformat(), moment="soir", plat="lasagne", mode="ajouter")

    assert execution.error is None
    assert planned_meals(sheet)["22/10/2026"] == ("", "Gratin de courgettes + Lasagnes")
    assert execution.response["precedent"] == "Gratin de courgettes"
    assert execution.undos == [
        MealUndo(date=TOMORROW, moment="soir", before="Gratin de courgettes", after="Gratin de courgettes + Lasagnes")
    ]


@pytest.mark.asyncio
async def test_add_mode_on_an_empty_slot_just_plans_the_dish(registry, sheet):
    execution = await _call(registry, "set_meal", date=TOMORROW.isoformat(), moment="midi", plat="Lasagnes", mode="ajouter")

    assert execution.error is None
    assert planned_meals(sheet)["22/10/2026"] == ("Lasagnes", "Gratin de courgettes")


@pytest.mark.asyncio
async def test_add_mode_refuses_a_dish_already_in_the_slot(registry, sheet):
    execution = await _call(registry, "set_meal", date=TOMORROW.isoformat(), moment="soir", plat="gratin de courgette",
                            mode="ajouter")

    assert "déjà prévu" in execution.error
    assert planned_meals(sheet)["22/10/2026"] == ("", "Gratin de courgettes")


@pytest.mark.asyncio
async def test_replace_stays_the_default_mode(registry, sheet):
    await _call(registry, "set_meal", date=TOMORROW.isoformat(), moment="soir", plat="Lasagnes")

    assert planned_meals(sheet)["22/10/2026"] == ("", "Lasagnes")


@pytest.mark.asyncio
async def test_clear_meal_empties_the_slot_and_can_be_undone(registry, sheet, connector):
    execution = await _call(registry, "clear_meal", date=TODAY.isoformat(), moment="midi")

    assert execution.error is None
    assert planned_meals(sheet)["21/10/2026"] == ("", "Risotto de quinoa")
    assert execution.response["retire"] == "Salade composée"
    assert execution.undos == [MealUndo(date=TODAY, moment="midi", before="Salade composée", after="")]

    tools = MealsTools(connector)
    tools.check_undo(execution.undos[0])
    tools.apply_undo(execution.undos[0])
    assert planned_meals(sheet)["21/10/2026"] == ("Salade composée", "Risotto de quinoa")


@pytest.mark.asyncio
async def test_clear_meal_on_an_empty_slot_fails_explicitly(registry):
    execution = await _call(registry, "clear_meal", date=TOMORROW.isoformat(), moment="midi")

    assert "Rien de prévu" in execution.error


def test_tool_descriptions_explain_add_versus_replace():
    tools = {t.name: t for t in meals_tool_definitions(MealsTools(None))}
    assert "ajouter" in tools["set_meal"].description
    assert "clear_meal" in tools
    schema = tools["set_meal"].args_model.model_json_schema()
    assert schema["properties"]["mode"]["enum"] == ["remplacer", "ajouter"]
