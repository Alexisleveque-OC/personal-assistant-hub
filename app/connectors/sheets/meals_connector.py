"""Connecteur Google Sheets pour les repas, recettes et courses (MealsShoppingConnector)."""
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
import unicodedata

try:
    import gspread
except ImportError:
    gspread = None

from app.config import settings
from app.connectors.base import BaseConnector
from app.connectors.sheets.models import (
    DayMealPlan,
    Recipe,
    ShoppingItem,
    WaitingListItem,
)


class MealsConnectorError(Exception):
    """Exception de base pour les opérations sur le connecteur repas et courses."""
    pass


class RecipeNotFoundError(MealsConnectorError):
    """Exception levée lorsqu'une recette est introuvable."""
    pass


class DayMealPlanNotFoundError(MealsConnectorError):
    """Exception levée lorsqu'aucun repas n'est trouvé pour une date."""
    pass


class PlanningWorksheetNotFoundError(DayMealPlanNotFoundError):
    """Exception explicite levée lorsqu'un onglet de planning annuel est introuvable."""
    pass


def resolve_meals_worksheet_name(available_worksheets: List[str], year: Optional[int] = None) -> str:
    """Résout dynamiquement le nom de l'onglet annuel (ex: 'repas 2026')."""
    target_year = year or datetime.now().year
    expected_name = f"repas {target_year}"
    if expected_name not in available_worksheets:
        raise PlanningWorksheetNotFoundError(
            f"L'onglet de planning annuel '{expected_name}' est introuvable dans le Google Sheet. "
            f"Veuillez créer l'onglet '{expected_name}' dans votre tableur pour l'année {target_year}. "
            f"Onglets actuellement disponibles : {available_worksheets}"
        )
    return expected_name


class MealsShoppingConnector(BaseConnector):
    """Connecteur métier pour la gestion du planning des repas, recettes et listes de courses."""

    def __init__(
        self,
        spreadsheet: Optional[Any] = None,
        credentials_path: Optional[str] = None,
    ) -> None:
        if spreadsheet is not None:
            self._spreadsheet = spreadsheet
        else:
            if gspread is None:
                raise RuntimeError("Le module gspread n'est pas installé.")
            cred_file = credentials_path or settings.google_service_account_file
            gc = gspread.service_account(filename=cred_file)
            self._spreadsheet = gc.open_by_key(settings.spreadsheet_meals_shopping_id)

        self._rayons_cache: Optional[Dict[str, str]] = None
        self._recipes_cache: Optional[List[Recipe]] = None

    @property
    def name(self) -> str:
        return "meals_shopping_connector"

    @property
    def spreadsheet(self) -> Any:
        return self._spreadsheet

    async def is_healthy(self) -> bool:
        """Vérifie si le Google Sheet est joignable et accessible."""
        try:
            return bool(self._spreadsheet.title)
        except Exception:
            return False

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalise une chaîne (minuscules, sans accents, sans espaces superflus)."""
        if not text:
            return ""
        normalized = unicodedata.normalize("NFKD", text)
        stripped = "".join(c for c in normalized if not unicodedata.combining(c))
        return " ".join(stripped.lower().split())

    def get_meal_plan(
        self,
        period: Optional[str] = None,
        target_date: Optional[str | date] = None,
    ) -> DayMealPlan:
        """Récupère le menu prévu pour une date ou une période relative."""
        # 1. Résolution de la date cible
        today = date.today()
        if target_date is not None:
            if isinstance(target_date, str):
                try:
                    resolved_date = datetime.strptime(target_date.strip(), "%d/%m/%Y").date()
                except ValueError:
                    resolved_date = datetime.strptime(target_date.strip(), "%Y-%m-%d").date()
            else:
                resolved_date = target_date
        elif period is not None:
            period_norm = period.strip().lower()
            if "demain" in period_norm:
                resolved_date = today + timedelta(days=1)
            else:
                resolved_date = today
        else:
            resolved_date = today

        year = resolved_date.year
        date_str_target = resolved_date.strftime("%d/%m/%Y")

        # 2. Résolution dynamique de l'onglet annuel
        available_worksheets = [ws.title for ws in self._spreadsheet.worksheets()]
        ws_name = resolve_meals_worksheet_name(available_worksheets, year=year)
        ws = self._spreadsheet.worksheet(ws_name)

        # 3. Recherche de la ligne de date
        rows = ws.get_all_values()
        for row in rows[1:]:
            if row and row[0].strip() == date_str_target:
                return DayMealPlan(
                    date_str=row[0].strip(),
                    day_name=row[1].strip() if len(row) > 1 else "",
                    lunch=row[2].strip() if len(row) > 2 and row[2].strip() else None,
                    dinner=row[3].strip() if len(row) > 3 and row[3].strip() else None,
                    notes=row[4].strip() if len(row) > 4 and row[4].strip() else None,
                )

        raise DayMealPlanNotFoundError(
            f"Aucun repas planifié pour la date {date_str_target} dans l'onglet '{ws_name}'."
        )

    def set_meal_plan(
        self,
        meal: str,
        target_date: str | date,
        meal_type: str = "soir",
    ) -> DayMealPlan:
        """Modifie le repas prévu pour une date donnée dans le planning annuel."""
        if isinstance(target_date, str):
            try:
                resolved_date = datetime.strptime(target_date.strip(), "%d/%m/%Y").date()
            except ValueError:
                resolved_date = datetime.strptime(target_date.strip(), "%Y-%m-%d").date()
        else:
            resolved_date = target_date

        year = resolved_date.year
        date_str_target = resolved_date.strftime("%d/%m/%Y")
        col_idx = 4 if meal_type.strip().lower() == "soir" else 3

        available_worksheets = [ws.title for ws in self._spreadsheet.worksheets()]
        ws_name = resolve_meals_worksheet_name(available_worksheets, year=year)
        ws = self._spreadsheet.worksheet(ws_name)

        rows = ws.get_all_values()
        found_idx = None
        matched_row = None
        for idx, row in enumerate(rows, start=1):
            if idx > 1 and row and row[0].strip() == date_str_target:
                found_idx = idx
                matched_row = list(row)
                break

        if found_idx is None:
            raise DayMealPlanNotFoundError(
                f"Date {date_str_target} introuvable dans l'onglet '{ws_name}' pour mise à jour."
            )

        ws.update_cell(found_idx, col_idx, meal)

        # Met à jour la représentation locale pour retourner le nouveau DayMealPlan
        while len(matched_row) < 5:
            matched_row.append("")
        if col_idx == 3:
            matched_row[2] = meal
        else:
            matched_row[3] = meal

        return DayMealPlan(
            date_str=matched_row[0].strip(),
            day_name=matched_row[1].strip(),
            lunch=matched_row[2].strip() if matched_row[2].strip() else None,
            dinner=matched_row[3].strip() if matched_row[3].strip() else None,
            notes=matched_row[4].strip() if len(matched_row) > 4 and matched_row[4].strip() else None,
        )

    def _get_all_recipes(self) -> List[Recipe]:
        """Charge et met en cache l'ensemble des recettes (standard et festives)."""
        if self._recipes_cache is not None:
            return self._recipes_cache

        recipes: List[Recipe] = []
        for sheet_name, is_festive in [("Recettes", False), ("Recette festive", True)]:
            try:
                ws = self._spreadsheet.worksheet(sheet_name)
                for row in ws.get_all_values()[1:]:
                    if row and row[0].strip():
                        ingredients = [item.strip() for item in row[4:] if item.strip()]
                        is_comp = row[3].strip().upper() == "TRUE" if len(row) > 3 else False
                        recipes.append(
                            Recipe(
                                name=row[0].strip(),
                                category=row[1].strip() if len(row) > 1 else None,
                                category_2=row[2].strip() if len(row) > 2 else None,
                                is_complete=is_comp,
                                is_festive=is_festive,
                                source_sheet=sheet_name,
                                ingredients=ingredients,
                            )
                        )
            except Exception:
                pass

        self._recipes_cache = recipes
        return self._recipes_cache

    def get_recipe_ingredients(self, recipe_name: str) -> Optional[Recipe]:
        """Recherche une recette et ses ingrédients dans le catalogue en cache."""
        query_norm = self._normalize(recipe_name)
        if not query_norm:
            return None

        all_recipes = self._get_all_recipes()

        # 1. Passe 1 : Recherche exacte
        for recipe in all_recipes:
            if self._normalize(recipe.name) == query_norm:
                return recipe

        # 2. Passe 2 : Recherche partielle (ex: 'risotto de quinoa' -> 'Risotto de Quinoa courgette')
        for recipe in all_recipes:
            rec_norm = self._normalize(recipe.name)
            if query_norm in rec_norm or rec_norm in query_norm:
                return recipe

        return None

    def _get_rayons_map(self) -> Dict[str, str]:
        """Charge le catalogue des rayons en cache mémoire pour économiser les quotas d'appels API."""
        if self._rayons_cache is not None:
            return self._rayons_cache

        cache: Dict[str, str] = {}
        # 1. Ingredients_Rayons
        try:
            ws_ing = self._spreadsheet.worksheet("Ingredients_Rayons")
            for row in ws_ing.get_all_values()[1:]:
                if row and len(row) >= 2 and row[0].strip():
                    cache[self._normalize(row[0])] = row[1].strip()
        except Exception:
            pass

        # 2. Hors_Repas
        try:
            ws_hr = self._spreadsheet.worksheet("Hors_Repas")
            for row in ws_hr.get_all_values()[1:]:
                if row and len(row) >= 3 and row[0].strip():
                    key = self._normalize(row[0])
                    if key not in cache:
                        cache[key] = row[2].strip() if row[2].strip() else "Divers"
        except Exception:
            pass

        self._rayons_cache = cache
        return self._rayons_cache

    def _resolve_rayon(self, item_name: str) -> tuple[str, Optional[str]]:
        """Déduit dynamiquement le rayon d'un article depuis le catalogue en cache."""
        norm_item = self._normalize(item_name)
        rayons_map = self._get_rayons_map()
        if norm_item in rayons_map:
            return rayons_map[norm_item], None

        return "Divers", f"Rayon non répertorié pour '{item_name}', classé temporairement en 'Divers'."

    def add_shopping_item(self, item: str) -> tuple[WaitingListItem, Optional[str]]:
        """Ajoute un article dans la liste d'attente (Liste_Attente)."""
        rayon, warning = self._resolve_rayon(item)
        today_str = date.today().strftime("%d/%m/%Y")

        ws = self._spreadsheet.worksheet("Liste_Attente")
        ws.append_row(["FALSE", item.strip(), today_str])

        item_obj = WaitingListItem(
            item=item.strip(),
            is_bought=False,
            added_at=today_str,
            rayon=rayon,
        )
        return item_obj, warning

    def add_recipe_ingredients_to_shopping_list(
        self,
        recipe_name: str,
        include_items: Optional[List[str]] = None,
        exclude_items: Optional[List[str]] = None,
    ) -> tuple[Recipe, List[WaitingListItem]]:
        """Ajoute les ingrédients d'une recette à la liste d'attente, avec support d'inclusions/exclusions."""
        recipe = self.get_recipe_ingredients(recipe_name)
        if recipe is None:
            raise RecipeNotFoundError(f"La recette '{recipe_name}' est introuvable.")

        candidates = list(recipe.ingredients)

        if include_items:
            inc_low = [self._normalize(inc) for inc in include_items]
            candidates = [
                ing for ing in candidates
                if any(inc in self._normalize(ing) for inc in inc_low)
            ]

        if exclude_items:
            exc_low = [self._normalize(exc) for exc in exclude_items]
            candidates = [
                ing for ing in candidates
                if not any(exc in self._normalize(ing) for exc in exc_low)
            ]

        added: List[WaitingListItem] = []
        for ingredient in candidates:
            item_obj, _ = self.add_shopping_item(ingredient)
            added.append(item_obj)

        return recipe, added

    def get_shopping_list(self) -> Dict[str, Any]:
        """Agrège les articles non achetés de 'Liste_Attente' et de 'Cette semaine'."""
        waiting_items: List[WaitingListItem] = []
        try:
            ws_wa = self._spreadsheet.worksheet("Liste_Attente")
            for row in ws_wa.get_all_values()[1:]:
                if row and len(row) >= 2 and row[1].strip():
                    is_bought = row[0].strip().upper() == "TRUE"
                    if not is_bought:
                        rayon, _ = self._resolve_rayon(row[1])
                        waiting_items.append(
                            WaitingListItem(
                                item=row[1].strip(),
                                is_bought=False,
                                added_at=row[2].strip() if len(row) > 2 else None,
                                rayon=rayon,
                            )
                        )
        except Exception:
            pass

        current_week_items: List[ShoppingItem] = []
        try:
            ws_cs = self._spreadsheet.worksheet("Cette semaine")
            rows = ws_cs.get_all_values()
            if len(rows) >= 10:
                for r_idx in range(9, len(rows)):
                    r = rows[r_idx]
                    for col_offset in [0, 2, 4, 6]:
                        if len(r) > col_offset + 1:
                            chk = r[col_offset].strip().upper()
                            name = r[col_offset + 1].strip()
                            if name and chk != "TRUE":
                                current_week_items.append(
                                    ShoppingItem(
                                        name=name,
                                        checked=False,
                                        destination_sheet="Cette semaine",
                                    )
                                )
        except Exception:
            pass

        return {
            "waiting_list": waiting_items,
            "current_week_items": current_week_items,
        }

    def mark_shopping_items_bought(self, items: List[str]) -> List[str]:
        """Coche comme acheté ('TRUE') les articles désignés dans 'Liste_Attente'."""
        ws = self._spreadsheet.worksheet("Liste_Attente")
        rows = ws.get_all_values()
        marked: List[str] = []
        items_norm = [self._normalize(it) for it in items]

        for idx, row in enumerate(rows[1:], start=2):
            if row and len(row) >= 2:
                if self._normalize(row[1]) in items_norm:
                    ws.update_cell(idx, 1, "TRUE")
                    marked.append(row[1].strip())

        return marked

    def clear_shopping_list(self, only_bought: bool = True) -> int:
        """Supprime les articles de 'Liste_Attente' (seulement ceux achetés par défaut)."""
        ws = self._spreadsheet.worksheet("Liste_Attente")
        rows = ws.get_all_values()
        if len(rows) <= 1:
            return 0

        to_delete: List[int] = []
        for idx, row in enumerate(rows[1:], start=2):
            if not row:
                continue
            if only_bought:
                if row[0].strip().upper() == "TRUE":
                    to_delete.append(idx)
            else:
                to_delete.append(idx)

        # Suppression de bas en haut pour préserver les numéros de ligne
        for row_idx in reversed(to_delete):
            ws.delete_rows(row_idx)

        return len(to_delete)

    async def execute_action(self, action_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Point d'entrée standardisé BaseConnector pour exécuter les actions."""
        if action_name == "get_meal_plan":
            plan = self.get_meal_plan(
                period=parameters.get("period"),
                target_date=parameters.get("target_date"),
            )
            return {"plan": plan.model_dump()}

        elif action_name == "get_recipe_ingredients":
            recipe = self.get_recipe_ingredients(recipe_name=parameters.get("recipe", ""))
            return {"recipe": recipe.model_dump() if recipe else None}

        elif action_name == "add_recipe_ingredients":
            recipe, added = self.add_recipe_ingredients_to_shopping_list(
                recipe_name=parameters.get("recipe", ""),
                include_items=parameters.get("include_items"),
                exclude_items=parameters.get("exclude_items"),
            )
            return {
                "recipe": recipe.model_dump(),
                "added_items": [it.model_dump() for it in added],
            }

        elif action_name == "set_meal_plan":
            plan = self.set_meal_plan(
                meal=parameters.get("meal", ""),
                target_date=parameters.get("target_date", date.today()),
                meal_type=parameters.get("meal_type", "soir"),
            )
            return {"plan": plan.model_dump()}

        elif action_name == "add_shopping_item":
            item, warning = self.add_shopping_item(item=parameters.get("item", ""))
            return {"item": item.model_dump(), "warning": warning}

        elif action_name == "get_shopping_list":
            res = self.get_shopping_list()
            return {
                "waiting_list": [it.model_dump() for it in res["waiting_list"]],
                "current_week_items": [it.model_dump() for it in res["current_week_items"]],
            }

        elif action_name == "mark_shopping_bought":
            marked = self.mark_shopping_items_bought(items=parameters.get("items", []))
            return {"marked": marked}

        elif action_name == "clear_shopping_list":
            count = self.clear_shopping_list(only_bought=parameters.get("only_bought", True))
            return {"deleted_count": count}

        else:
            raise ValueError(f"Action '{action_name}' non reconnue par MealsShoppingConnector.")
