"""Modèles Pydantic pour la structure et les données du Google Sheet Repas & Courses."""
from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class DayMealPlan(BaseModel):
    """Représente le menu d'une journée dans la feuille annuelle (ex: 'repas 2026')."""
    date_str: str = Field(description="Date au format JJ/MM/AAAA telle qu'écrite dans le Sheet")
    day_name: str = Field(description="Nom du jour de la semaine (ex: Lundi, Mardi)")
    lunch: Optional[str] = Field(default=None, description="Plat prévu pour le midi")
    dinner: Optional[str] = Field(default=None, description="Plat prévu pour le soir")
    notes: Optional[str] = Field(default=None, description="Notes ou magasin associé")

    @field_validator("lunch", "dinner", "notes", mode="before")
    @classmethod
    def clean_empty_strings(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    def parse_date(self) -> date:
        """Convertit la date_str JJ/MM/AAAA en objet date Python."""
        return datetime.strptime(self.date_str.strip(), "%d/%m/%Y").date()


class Recipe(BaseModel):
    """Représente une recette dans l'onglet 'Recettes' ou 'Recette festive'."""
    name: str = Field(description="Nom du plat / recette")
    category: Optional[str] = Field(default=None, description="Catégorie principale (ex: Féculents, Apéro, Gâteau)")
    category_2: Optional[str] = Field(default=None, description="Catégorie secondaire")
    is_complete: bool = Field(default=False, description="Repas complet ou non")
    is_festive: bool = Field(default=False, description="Indique si la recette provient de 'Recette festive'")
    source_sheet: str = Field(default="Recettes", description="Feuille source ('Recettes' ou 'Recette festive')")
    ingredients: List[str] = Field(default_factory=list, description="Liste des ingrédients requis")


class ShoppingItem(BaseModel):
    """Représente un article dans la liste de courses."""
    name: str = Field(description="Nom de l'article ou ingrédient")
    checked: bool = Field(default=False, description="Case à cocher (fait / acheté)")
    rayon: Optional[str] = Field(default=None, description="Rayon du magasin")
    destination_sheet: str = Field(default="Cette semaine", description="Feuille cible ('Cette semaine' ou 'Courses festives')")


class RayonSetting(BaseModel):
    """Ordre de tri et configuration d'un rayon de magasin."""
    name: str = Field(description="Nom du rayon")
    order: int = Field(description="Ordre d'affichage dans les courses")


class SheetSchemaSnapshot(BaseModel):
    """Contrat de structure officiel du Google Sheet partagé."""
    planning_headers: List[str] = Field(
        default=["Date", "Jour", "Midi", "Soir", "Notes / Magasin"],
        description="En-têtes obligatoires de la feuille annuelle repas",
    )
    recipes_headers: List[str] = Field(
        default=["Plat", "Catégorie", "Catégorie 2", "Complet", "Ingrédient"],
        description="En-têtes de l'onglet Recettes et Recette festive",
    )
    rayons_headers: List[str] = Field(
        default=["Rayons", "Ordre"],
        description="En-têtes de l'onglet Rayons",
    )
    hors_repas_headers: List[str] = Field(
        default=["Nom", "pré-cocher?", "rayon"],
        description="En-têtes de l'onglet Hors_Repas",
    )
    ingredients_rayons_headers: List[str] = Field(
        default=["Ingrédient", "Rayon"],
        description="En-têtes de l'onglet Ingredients_Rayons",
    )
    required_worksheets: List[str] = Field(
        default=[
            "Cette semaine",
            "Recettes",
            "Recette festive",
            "Courses festives",
            "Rayons",
            "Hors_Repas",
            "Ingredients_Rayons",
        ],
        description="Onglets obligatoires permanents (hors feuille annuelle dynamique)",
    )
