"""Connecteur Google Sheets pour les repas, recettes et courses (MealsShoppingConnector)."""
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import re
import unicodedata
import logging
import time
import json
import base64

logger = logging.getLogger(__name__)

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
            if getattr(settings, "google_service_account_info", None) and settings.google_service_account_info.strip():
                raw_info = settings.google_service_account_info.strip()
                if raw_info.startswith("{"):
                    info_dict = json.loads(raw_info)
                else:
                    try:
                        decoded = base64.b64decode(raw_info).decode("utf-8")
                        info_dict = json.loads(decoded)
                    except Exception:
                        info_dict = json.loads(raw_info)
                gc = gspread.service_account_from_dict(info_dict)
            else:
                cred_file = credentials_path or settings.google_service_account_file
                gc = gspread.service_account(filename=cred_file)
            self._spreadsheet = gc.open_by_key(settings.spreadsheet_meals_shopping_id)

        self._rayons_cache: Optional[Dict[str, str]] = None
        self._recipes_cache: Optional[List[Recipe]] = None
        self._shopping_cache: Optional[Dict[str, Any]] = None
        self._shopping_cache_time: float = 0.0
        self._week_meals_cache: Optional[List[Dict[str, Any]]] = None
        self._week_meals_cache_time: float = 0.0
        self._rayons_order: Optional[Dict[str, int]] = None
        self._cache_ttl_seconds: int = 180

    def invalidate_cache(self, domain: Optional[str] = None) -> None:
        """Invalide le cache mémoire pour un domaine ('shopping', 'meals', 'recipes') ou tout."""
        if domain in (None, "shopping"):
            self._shopping_cache = None
            self._shopping_cache_time = 0.0
        if domain in (None, "meals"):
            self._week_meals_cache = None
            self._week_meals_cache_time = 0.0
        if domain in (None, "recipes"):
            self._recipes_cache = None

    def get_rayons_order(self) -> Dict[str, int]:
        """Charge et met en cache l'ordre des rayons défini dans l'onglet 'Rayons'."""
        if getattr(self, "_rayons_order", None) is not None:
            return self._rayons_order

        order_map: Dict[str, int] = {}
        try:
            ws = self._spreadsheet.worksheet("Rayons")
            for row in ws.get_all_values()[1:]:
                if row and len(row) >= 2 and row[0].strip():
                    try:
                        order_map[row[0].strip()] = int(row[1].strip())
                    except ValueError:
                        order_map[row[0].strip()] = 999
        except Exception:
            pass

        self._rayons_order = order_map
        return self._rayons_order

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

    def get_next_meal_plan(
        self,
        now: Optional[datetime] = None,
    ) -> Tuple[DayMealPlan, str, str, str]:
        """Détecte intelligemment le prochain repas réel non vide.
        
        Retourne : (plan, meal_type, label_moment, dish_name)
        """
        ref_dt = now or datetime.now()
        current_hour = ref_dt.hour + ref_dt.minute / 60.0
        today = ref_dt.date()
        tomorrow = today + timedelta(days=1)

        # 1. Essayer aujourd'hui
        try:
            today_plan = self.get_meal_plan(target_date=today)
        except DayMealPlanNotFoundError:
            today_plan = None

        if today_plan:
            if current_hour < 14.0:
                if today_plan.lunch:
                    return today_plan, "lunch", "ce midi", today_plan.lunch
                elif today_plan.dinner:
                    return today_plan, "dinner", "ce soir", today_plan.dinner
            elif current_hour < 21.5:
                if today_plan.dinner:
                    return today_plan, "dinner", "ce soir", today_plan.dinner

        # 2. Chercher demain
        try:
            tomorrow_plan = self.get_meal_plan(target_date=tomorrow)
        except DayMealPlanNotFoundError:
            tomorrow_plan = None

        if tomorrow_plan:
            if tomorrow_plan.lunch:
                return tomorrow_plan, "lunch", "demain midi", tomorrow_plan.lunch
            elif tomorrow_plan.dinner:
                return tomorrow_plan, "dinner", "demain soir", tomorrow_plan.dinner

        # 3. Repli si aucun repas n'est planifié
        if today_plan:
            return today_plan, "dinner", "ce soir", "Rien de planifié"
        elif tomorrow_plan:
            return tomorrow_plan, "lunch", "demain midi", "Rien de planifié"

        raise DayMealPlanNotFoundError("Aucun repas planifié trouvé pour aujourd'hui ou demain.")

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
        self.invalidate_cache("meals")

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

    def get_week_meal_plans(self) -> List[Dict[str, Any]]:
        """Récupère les repas prévus pour les 7 jours de la semaine courante avec leurs ingrédients."""
        now = time.time()
        if getattr(self, "_week_meals_cache", None) is not None and (
            now - getattr(self, "_week_meals_cache_time", 0.0) < getattr(self, "_cache_ttl_seconds", 180)
        ):
            return self._week_meals_cache

        days_list: List[Dict[str, Any]] = []
        today = date.today()
        today_day_num = today.day

        try:
            ws_cs = self._spreadsheet.worksheet("Cette semaine")
            rows = ws_cs.get_all_values()
            # Lignes 2 à 8 : planning de la semaine (7 jours)
            for r_idx in range(1, min(8, len(rows))):
                row = rows[r_idx]
                if not row or not row[0].strip():
                    continue
                day_label = row[0].strip()  # ex: 'sam. 19', 'mar. 22'
                lunch = row[2].strip() if len(row) > 2 and row[2].strip() else None
                dinner = row[4].strip() if len(row) > 4 and row[4].strip() else None

                # Détection si c'est aujourd'hui
                is_today = False
                match_day = re.search(r"\b(\d{1,2})\b", day_label)
                if match_day and int(match_day.group(1)) == today_day_num:
                    is_today = True

                # Ingrédients pour le midi
                lunch_ing: List[str] = []
                if lunch:
                    rec = self.get_recipe_ingredients(lunch)
                    if rec:
                        lunch_ing = rec.ingredients
                    else:
                        for part in re.split(r"\+|\bet\b", lunch):
                            rec_part = self.get_recipe_ingredients(part.strip())
                            if rec_part:
                                lunch_ing.extend(rec_part.ingredients)

                # Ingrédients pour le soir
                dinner_ing: List[str] = []
                if dinner:
                    rec = self.get_recipe_ingredients(dinner)
                    if rec:
                        dinner_ing = rec.ingredients
                    else:
                        for part in re.split(r"\+|\bet\b", dinner):
                            rec_part = self.get_recipe_ingredients(part.strip())
                            if rec_part:
                                dinner_ing.extend(rec_part.ingredients)

                days_list.append({
                    "day_label": day_label,
                    "lunch": lunch,
                    "lunch_ingredients": list(dict.fromkeys(lunch_ing)),
                    "dinner": dinner,
                    "dinner_ingredients": list(dict.fromkeys(dinner_ing)),
                    "is_today": is_today,
                })
        except Exception as e:
            logger.warning(f"Impossible de lire le planning de 'Cette semaine': {e}")

        self._week_meals_cache = days_list
        self._week_meals_cache_time = now
        return days_list

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
        norm_item_clean = re.sub(r"^(?:du|de\s+la|des|le|la|les|l'|un|une|d')\s+", "", norm_item).strip()
        rayons_map = self._get_rayons_map()

        if norm_item in rayons_map:
            return rayons_map[norm_item], None
        if norm_item_clean in rayons_map:
            return rayons_map[norm_item_clean], None

        # Recherche par sous-chaîne pour les articles composés
        for cat_item, rayon in rayons_map.items():
            if norm_item_clean == cat_item or (len(cat_item) > 3 and cat_item in norm_item_clean):
                return rayon, None

        return "Divers", f"Rayon non répertorié pour '{item_name}', classé temporairement en 'Divers'."

    def ensure_checkbox_validation(self) -> None:
        """Garantit que la colonne A de Liste_Attente (à partir de la ligne 2) possède la validation case à cocher."""
        if not self._spreadsheet:
            return
        try:
            ws = self._spreadsheet.worksheet("Liste_Attente")
            body = {
                "requests": [
                    {
                        "setDataValidation": {
                            "range": {
                                "sheetId": ws.id,
                                "startRowIndex": 1,        # Ligne 2 (0-indexed)
                                "startColumnIndex": 0,     # Colonne A
                                "endColumnIndex": 1,
                            },
                            "rule": {
                                "condition": {
                                    "type": "BOOLEAN"
                                },
                                "showCustomUi": True,
                                "strict": True,
                            },
                        }
                    }
                ]
            }
            if hasattr(self._spreadsheet, "batch_update"):
                self._spreadsheet.batch_update(body)
        except Exception:
            pass

    def add_shopping_items(self, items: List[str]) -> tuple[List[WaitingListItem], List[str]]:
        """Ajoute une liste d'articles dans Liste_Attente avec case à cocher native."""
        today_str = date.today().strftime("%d/%m/%Y")
        ws = self._spreadsheet.worksheet("Liste_Attente")
        self.ensure_checkbox_validation()

        added_items: List[WaitingListItem] = []
        warnings: List[str] = []
        rows_to_append: List[List[Any]] = []

        for raw_item in items:
            cleaned = re.sub(
                r"^(?:du|de\s+la|des|de\s+l[' ]|d[' ]|le|la|les|l[' ]|un[e]?)\s+",
                "",
                raw_item.strip(),
                flags=re.IGNORECASE,
            ).strip()
            clean_item = (cleaned[0].upper() + cleaned[1:]) if cleaned else raw_item.strip()
            rayon, warning = self._resolve_rayon(clean_item)
            if warning:
                warnings.append(warning)

            # False (booléen Python) avec USER_ENTERED pour case à cocher native
            rows_to_append.append([False, clean_item, today_str])
            added_items.append(
                WaitingListItem(
                    item=clean_item,
                    is_bought=False,
                    added_at=today_str,
                    rayon=rayon,
                )
            )

        if len(rows_to_append) == 1:
            ws.append_row(rows_to_append[0], value_input_option="USER_ENTERED")
        elif hasattr(ws, "append_rows") and callable(ws.append_rows):
            ws.append_rows(rows_to_append, value_input_option="USER_ENTERED")
        else:
            for row in rows_to_append:
                ws.append_row(row, value_input_option="USER_ENTERED")

        self.invalidate_cache("shopping")
        return added_items, warnings

    def add_shopping_item(self, item: str) -> tuple[WaitingListItem, Optional[str]]:
        """Ajoute un article unique dans la liste d'attente (Liste_Attente)."""
        items, warnings = self.add_shopping_items([item])
        warning = warnings[0] if warnings else None
        return items[0], warning

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

        def _clean_token(t: str) -> str:
            t_norm = self._normalize(t)
            return re.sub(r"^(?:du|de\s+la|des|le|la|les|l'|un|une|d')\s+", "", t_norm, flags=re.IGNORECASE).strip()

        if include_items:
            flat_inc: List[str] = []
            for inc in include_items:
                for part in re.split(r",|\bet\b", inc):
                    token = _clean_token(part)
                    if token:
                        flat_inc.append(token)

            candidates = [
                ing for ing in candidates
                if any(inc in self._normalize(ing) or self._normalize(ing) in inc for inc in flat_inc)
            ]

        if exclude_items:
            flat_exc: List[str] = []
            for exc in exclude_items:
                for part in re.split(r",|\bet\b", exc):
                    token = _clean_token(part)
                    if token:
                        flat_exc.append(token)

            candidates = [
                ing for ing in candidates
                if not any(exc in self._normalize(ing) or self._normalize(ing) in exc for exc in flat_exc)
            ]

        added: List[WaitingListItem] = []
        for ingredient in candidates:
            item_obj, _ = self.add_shopping_item(ingredient)
            added.append(item_obj)

        return recipe, added

    def get_shopping_list(self) -> Dict[str, Any]:
        """Agrège les articles non achetés de 'Liste_Attente' et de 'Cette semaine'."""
        now = time.time()
        if getattr(self, "_shopping_cache", None) is not None and (
            now - getattr(self, "_shopping_cache_time", 0.0) < getattr(self, "_cache_ttl_seconds", 180)
        ):
            return self._shopping_cache

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
                current_rayons: Dict[int, str] = {}
                for r_idx in range(9, len(rows)):
                    r = rows[r_idx]
                    for col_offset in [0, 2, 4, 6]:
                        if len(r) > col_offset:
                            val0 = r[col_offset].strip()
                            val1 = r[col_offset + 1].strip() if len(r) > col_offset + 1 else ""
                            if val0 and val0.upper() not in ["TRUE", "FALSE"] and not val1:
                                current_rayons[col_offset] = val0
                            elif val1:
                                is_chk = val0.upper() == "TRUE"
                                current_week_items.append(
                                    ShoppingItem(
                                        name=val1,
                                        checked=is_chk,
                                        rayon=current_rayons.get(col_offset),
                                        destination_sheet="Cette semaine",
                                    )
                                )
        except Exception:
            pass

        res = {
            "waiting_list": waiting_items,
            "current_week_items": current_week_items,
            "rayons_order": self.get_rayons_order(),
        }
        self._shopping_cache = res
        self._shopping_cache_time = now
        return res

    def mark_shopping_items_bought(
        self,
        items: Optional[List[str]] = None,
        mark_all: bool = False,
    ) -> List[str]:
        """Coche comme acheté ('TRUE') les articles désignés dans 'Liste_Attente' (ou tous si mark_all=True)."""
        ws = self._spreadsheet.worksheet("Liste_Attente")
        rows = ws.get_all_values()
        marked: List[str] = []
        items_norm = [self._normalize(it) for it in items] if items else []

        for idx, row in enumerate(rows[1:], start=2):
            if row and len(row) >= 2 and row[1].strip():
                if mark_all or (self._normalize(row[1]) in items_norm):
                    ws.update_cell(idx, 1, "TRUE")
                    marked.append(row[1].strip())

        self.invalidate_cache("shopping")
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

        self.invalidate_cache("shopping")
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

        elif action_name == "add_shopping_items":
            items, warnings = self.add_shopping_items(items=parameters.get("items", []))
            return {"items": [it.model_dump() for it in items], "warnings": warnings}

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
