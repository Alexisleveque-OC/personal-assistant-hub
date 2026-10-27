"""Déclaration des outils Repas & Courses exposés à l'agent."""
from typing import List

from app.core.agent.tool_registry import AgentTool
from app.core.agent.tools.meals_models import (
    AddShoppingItemsArgs,
    CheckShoppingItemsArgs,
    ClearBoughtArgs,
    GetMealPlanArgs,
    GetRecipeArgs,
    GetShoppingListArgs,
    RemoveShoppingItemsArgs,
    SetMealArgs,
)
from app.core.agent.tools.meals_tools import MealsTools


def meals_tool_definitions(tools: MealsTools) -> List[AgentTool]:
    return [
        AgentTool(
            name="get_shopping_list",
            description=(
                "Lit la liste de courses : liste d'attente (articles ajoutés à la demande) et liste de la semaine "
                "(issue du planning des repas), avec rayon et état coché."
            ),
            args_model=GetShoppingListArgs,
            handler=tools.get_shopping_list,
        ),
        AgentTool(
            name="add_shopping_items",
            description=(
                "Ajoute des articles à la liste d'attente des courses. Le rayon est déduit du catalogue. "
                "Les articles au rayon inconnu ne sont PAS ajoutés (rayon_a_demander) : l'application demandera "
                "elle-même le rayon à l'utilisateur juste après ta réponse. Ne choisis pas de rayon, ne rappelle pas "
                "l'outil pour eux et ne pose pas la question toi-même."
            ),
            args_model=AddShoppingItemsArgs,
            handler=tools.add_shopping_items,
        ),
        AgentTool(
            name="check_shopping_items",
            description="Coche (acheté) ou décoche des articles, dans la liste d'attente comme dans celle de la semaine.",
            args_model=CheckShoppingItemsArgs,
            handler=tools.check_shopping_items,
        ),
        AgentTool(
            name="remove_shopping_items",
            description="Retire des articles de la liste d'attente (la liste de la semaine se coche, elle ne se modifie pas).",
            args_model=RemoveShoppingItemsArgs,
            handler=tools.remove_shopping_items,
        ),
        AgentTool(
            name="clear_bought_shopping_items",
            description="Vide la liste de courses : supprime uniquement les articles déjà cochés de la liste d'attente.",
            args_model=ClearBoughtArgs,
            handler=tools.clear_bought_shopping_items,
        ),
        AgentTool(
            name="get_meal_plan",
            description="Lit le planning des repas (midi et soir) sur une période de 14 jours maximum.",
            args_model=GetMealPlanArgs,
            handler=tools.get_meal_plan,
        ),
        AgentTool(
            name="set_meal",
            description=(
                "Planifie ou remplace le plat d'un repas (midi ou soir) à une date. Le nom est aligné sur le carnet "
                "de recettes ; un plat absent du carnet exige la confirmation de l'utilisateur."
            ),
            args_model=SetMealArgs,
            handler=tools.set_meal,
        ),
        AgentTool(
            name="get_recipe",
            description=(
                "Lit une recette du carnet et ses ingrédients. Pour ajouter les ingrédients aux courses, "
                "lis la recette puis appelle add_shopping_items avec les ingrédients voulus."
            ),
            args_model=GetRecipeArgs,
            handler=tools.get_recipe,
        ),
    ]
