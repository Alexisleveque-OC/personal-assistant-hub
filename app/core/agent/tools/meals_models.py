"""Contrats Pydantic stricts des outils Repas & Courses de l'agent (arguments, vues et instantanés d'annulation)."""
from datetime import date as dt_date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.connectors.sheets.models import WaitingListItem
from app.core.agent.tools.sport_models import StrictArgs

MealMoment = Literal["midi", "soir"]


# --- Arguments --------------------------------------------------------------------------------------------------

class GetShoppingListArgs(StrictArgs):
    rayon: Optional[str] = Field(None, description="Ne garder que ce rayon (ex. Frais).")
    inclure_coches: bool = Field(False, description="Inclure aussi les articles déjà cochés (achetés).")


class ShoppingArticleArg(StrictArgs):
    nom: str = Field(min_length=1, pattern=r"\S", description="Nom de l'article en français, sans quantité superflue.")
    rayon: Optional[str] = Field(
        None, description="Rayon du magasin, uniquement s'il est dit par l'utilisateur ou choisi dans rayons_disponibles.",
    )


class AddShoppingItemsArgs(StrictArgs):
    articles: List[ShoppingArticleArg] = Field(min_length=1, max_length=30)


class CheckShoppingItemsArgs(StrictArgs):
    noms: List[str] = Field(min_length=1, max_length=30, description="Articles à cocher (ou décocher).")
    coche: bool = Field(True, description="true : marquer acheté ; false : décocher.")


class RemoveShoppingItemsArgs(StrictArgs):
    noms: List[str] = Field(min_length=1, max_length=30, description="Articles à retirer de la liste d'attente.")


class ClearBoughtArgs(StrictArgs):
    """Aucun argument : supprime les articles déjà cochés de la liste d'attente."""


class GetMealPlanArgs(StrictArgs):
    date_debut: dt_date
    date_fin: Optional[dt_date] = Field(None, description="Dernier jour inclus (par défaut : date_debut). 14 jours maximum.")


class SetMealArgs(StrictArgs):
    date: dt_date
    moment: MealMoment
    plat: str = Field(min_length=1, pattern=r"\S", description="Plat prévu, de préférence tel que nommé dans le carnet de recettes.")
    hors_carnet_confirme: bool = Field(
        False, description="true seulement si l'utilisateur a confirmé vouloir un plat absent du carnet de recettes.",
    )


class GetRecipeArgs(StrictArgs):
    nom: str = Field(min_length=1, pattern=r"\S", description="Nom de la recette.")


# --- Vues renvoyées au modèle -----------------------------------------------------------------------------------

class ShoppingArticle(BaseModel):
    nom: str
    rayon: Optional[str] = None
    liste: Literal["attente", "semaine"]
    coche: bool


class ShoppingListView(BaseModel):
    articles: List[ShoppingArticle]


class MealDay(BaseModel):
    date: dt_date
    jour: str
    midi: Optional[str] = None
    soir: Optional[str] = None


class MealPlanView(BaseModel):
    jours: List[MealDay]
    absents: List[dt_date] = Field(default_factory=list, description="Dates absentes du planning.")


class RecipeView(BaseModel):
    nom: str
    ingredients: List[str]


# --- Instantanés d'annulation -----------------------------------------------------------------------------------

class ShoppingAddedUndo(BaseModel):
    kind: Literal["shopping_added"] = "shopping_added"
    items: List[str]


class ShoppingCheckedUndo(BaseModel):
    """`checked` : état appliqué par l'agent ; l'annulation rétablit l'état inverse."""
    kind: Literal["shopping_checked"] = "shopping_checked"
    checked: bool
    waiting: List[str] = Field(default_factory=list)
    week: List[str] = Field(default_factory=list)


class ShoppingRemovedUndo(BaseModel):
    kind: Literal["shopping_removed"] = "shopping_removed"
    items: List[WaitingListItem]


class MealUndo(BaseModel):
    kind: Literal["meal_set"] = "meal_set"
    date: dt_date
    moment: MealMoment
    before: Optional[str] = None
    after: str


# --- Résultats des mutations ------------------------------------------------------------------------------------

class ShoppingAdded(BaseModel):
    ajoutes: List[ShoppingArticle]
    rayon_a_choisir: List[str] = Field(description="Articles NON ajoutés : rayon inconnu, à choisir dans rayons_disponibles.")
    rayons_disponibles: List[str]
    undos: List[ShoppingAddedUndo]


class ShoppingChecked(BaseModel):
    modifies: List[str]
    deja_dans_cet_etat: List[str]
    introuvables: List[str]
    coche: bool
    undos: List[ShoppingCheckedUndo]


class ShoppingRemoved(BaseModel):
    retires: List[str]
    introuvables: List[str] = Field(default_factory=list)
    remarque: Optional[str] = None
    undos: List[ShoppingRemovedUndo]


class MealSet(BaseModel):
    jour: MealDay
    precedent: Optional[str] = None
    recette_connue: bool
    undos: List[MealUndo]
