"""Outils métier Repas & Courses de l'agent : lecture et mutations via `MealsShoppingConnector`.

Chaque écriture passe par le connecteur, qui invalide son cache mémoire (quotas Google Sheets),
et produit un instantané permettant l'annulation exacte. Rien n'est deviné en silence :
un rayon inconnu est renvoyé au modèle, un plat hors carnet exige une confirmation.
"""
from datetime import date, timedelta
from typing import Collection, List, Optional, Union

from app.connectors.sheets.meals_connector import (
    DayMealPlanNotFoundError,
    MealsShoppingConnector,
    PlanningWorksheetNotFoundError,
)
from app.connectors.sheets.models import WaitingListItem
from app.core.agent.tools.meals_models import (
    AddShoppingItemsArgs,
    CheckShoppingItemsArgs,
    ClearBoughtArgs,
    GetMealPlanArgs,
    GetRecipeArgs,
    GetShoppingListArgs,
    MealDay,
    MealPlanView,
    MealSet,
    MealUndo,
    RecipeView,
    RemoveShoppingItemsArgs,
    SetMealArgs,
    ShoppingAdded,
    ShoppingAddedUndo,
    ShoppingArticle,
    ShoppingChecked,
    ShoppingCheckedUndo,
    ShoppingListView,
    ShoppingRemoved,
    ShoppingRemovedUndo,
)
from app.core.agent.tools.sport_models import WEEKDAYS_FR
from app.core.agent.tools.tool_error import ToolError

MAX_MEAL_PLAN_DAYS = 14

MealsUndo = Union[ShoppingAddedUndo, ShoppingCheckedUndo, ShoppingRemovedUndo, MealUndo]


class MealsToolError(ToolError):
    """Erreur métier Repas & Courses renvoyée telle quelle au modèle."""


class MealsTools:
    def __init__(self, connector: Optional[MealsShoppingConnector], confirmable_dishes: Collection[str] = ()) -> None:
        """`confirmable_dishes` : plats hors carnet refusés au tour précédent, donc soumis à l'utilisateur.

        `hors_carnet_confirme` n'est accepté que pour eux : le modèle ne peut pas se confirmer lui-même.
        Les plats refusés pendant ce tour sont exposés dans `refused_dishes` pour le tour suivant.
        """
        self._connector = connector
        self._confirmable = {dish.strip().casefold() for dish in confirmable_dishes}
        self.refused_dishes: List[str] = []

    @property
    def connector(self) -> MealsShoppingConnector:
        if self._connector is None:
            raise MealsToolError("Le classeur Repas & Courses est indisponible (connecteur Google Sheets non configuré).")
        return self._connector

    # --- Courses ------------------------------------------------------------------------------------------------

    def get_shopping_list(self, args: GetShoppingListArgs) -> ShoppingListView:
        shopping = self.connector.get_shopping_list()
        if args.inclure_coches:
            # La vue en cache ne contient que les articles non achetés de la liste d'attente.
            waiting = [
                ShoppingArticle(nom=row.item, rayon=self.connector.resolve_rayon(row.item)[0], liste="attente", coche=row.is_bought)
                for row in self.connector.get_waiting_list_rows()
            ]
        else:
            waiting = [
                ShoppingArticle(nom=it.item, rayon=it.rayon, liste="attente", coche=False)
                for it in shopping.get("waiting_list", [])
            ]
        week = [
            ShoppingArticle(nom=it.name, rayon=it.rayon, liste="semaine", coche=it.checked)
            for it in shopping.get("current_week_items", [])
            if args.inclure_coches or not it.checked
        ]
        articles = waiting + week
        if args.rayon:
            wanted = args.rayon.casefold()
            articles = [
                a for a in articles
                if a.rayon and (self.connector.matches_item_name(args.rayon, a.rayon) or wanted in a.rayon.casefold())
            ]
        return ShoppingListView(articles=articles)

    def add_shopping_items(self, args: AddShoppingItemsArgs) -> ShoppingAdded:
        available = self.connector.get_available_rayons()
        explicit = {}
        for article in args.articles:
            if article.rayon:
                explicit[article.nom.strip()] = self._canonical_rayon(article.rayon, available)

        to_add: List[str] = []
        to_choose: List[str] = []
        for article in args.articles:
            name = article.nom.strip()
            if name not in explicit and self.connector.resolve_rayon(name)[1]:
                to_choose.append(name)
            else:
                to_add.append(name)

        added: List[WaitingListItem] = []
        if to_add:
            added, _ = self.connector.add_shopping_items(to_add, rayons=explicit or None)
        return ShoppingAdded(
            ajoutes=[ShoppingArticle(nom=it.item, rayon=it.rayon, liste="attente", coche=False) for it in added],
            rayon_a_choisir=to_choose,
            rayons_disponibles=available,
            undos=[ShoppingAddedUndo(items=[it.item for it in added])] if added else [],
        )

    def check_shopping_items(self, args: CheckShoppingItemsArgs) -> ShoppingChecked:
        waiting_rows = self.connector.get_waiting_list_rows()
        week_items = self.connector.get_shopping_list().get("current_week_items", [])
        waiting: List[str] = []
        week: List[str] = []
        changed: List[str] = []
        unchanged: List[str] = []
        unknown: List[str] = []
        for query in args.noms:
            w_matches = [r for r in waiting_rows if self.connector.matches_item_name(query, r.item)]
            k_matches = [i for i in week_items if self.connector.matches_item_name(query, i.name)]
            w_todo = [r.item for r in w_matches if r.is_bought != args.coche and r.item not in waiting]
            k_todo = [i.name for i in k_matches if i.checked != args.coche and i.name not in week]
            if w_todo or k_todo:
                waiting += w_todo
                week += k_todo
                changed += w_todo + k_todo
            elif w_matches or k_matches:
                unchanged.append(query)
            else:
                unknown.append(query)

        self._set_checked(args.coche, waiting, week)
        undos = [ShoppingCheckedUndo(checked=args.coche, waiting=waiting, week=week)] if changed else []
        return ShoppingChecked(
            modifies=changed, deja_dans_cet_etat=unchanged, introuvables=unknown, coche=args.coche, undos=undos,
        )

    def remove_shopping_items(self, args: RemoveShoppingItemsArgs) -> ShoppingRemoved:
        rows = self.connector.get_waiting_list_rows()
        week_items = self.connector.get_shopping_list().get("current_week_items", [])
        removed: List[WaitingListItem] = []
        unknown: List[str] = []
        week_only: List[str] = []
        for query in args.noms:
            matches = [r for r in rows if self.connector.matches_item_name(query, r.item) and r not in removed]
            if not matches:
                unknown.append(query)
                if any(self.connector.matches_item_name(query, i.name) for i in week_items):
                    week_only.append(query)
            removed += matches
        for row in removed:
            self.connector.remove_shopping_item(row.item)

        remarque = None
        if week_only:
            remarque = (
                f"{', '.join(week_only)} : article(s) de la liste de la semaine, issue du planning des repas ; "
                "on peut seulement les cocher."
            )
        return ShoppingRemoved(
            retires=[r.item for r in removed], introuvables=unknown, remarque=remarque,
            undos=[ShoppingRemovedUndo(items=removed)] if removed else [],
        )

    def clear_bought_shopping_items(self, _: ClearBoughtArgs) -> ShoppingRemoved:
        bought = [row for row in self.connector.get_waiting_list_rows() if row.is_bought]
        if bought:
            self.connector.clear_shopping_list(only_bought=True)
        return ShoppingRemoved(
            retires=[row.item for row in bought], undos=[ShoppingRemovedUndo(items=bought)] if bought else [],
        )

    # --- Repas & recettes ---------------------------------------------------------------------------------------

    def get_meal_plan(self, args: GetMealPlanArgs) -> MealPlanView:
        last = args.date_fin or args.date_debut
        if last < args.date_debut:
            raise MealsToolError(f"date_fin ({last}) doit suivre date_debut ({args.date_debut}).")
        span = (last - args.date_debut).days + 1
        if span > MAX_MEAL_PLAN_DAYS:
            raise MealsToolError(f"Période trop longue ({span} jours) : {MAX_MEAL_PLAN_DAYS} jours maximum par lecture.")

        days: List[MealDay] = []
        missing: List[date] = []
        for offset in range(span):
            day = args.date_debut + timedelta(days=offset)
            plan = self._day_plan(day)
            if plan is None:
                missing.append(day)
            else:
                days.append(plan)
        return MealPlanView(jours=days, absents=missing)

    def set_meal(self, args: SetMealArgs) -> MealSet:
        recipe = self.connector.get_recipe_ingredients(args.plat)
        confirmed = args.hors_carnet_confirme and args.plat.strip().casefold() in self._confirmable
        if recipe is None and not confirmed:
            if args.plat.strip() not in self.refused_dishes:
                self.refused_dishes.append(args.plat.strip())
            raise MealsToolError(
                f"« {args.plat} » n'est pas dans le carnet de recettes : demande confirmation à l'utilisateur et "
                "termine ton tour ; s'il confirme, rappelle set_meal avec hors_carnet_confirme=true au tour suivant."
            )
        dish = recipe.name if recipe else args.plat.strip()
        current = self._day_plan(args.date)
        if current is None:
            raise MealsToolError(f"Le {args.date:%d/%m/%Y} est absent du planning des repas : impossible d'y planifier un plat.")
        before = current.midi if args.moment == "midi" else current.soir

        updated = self.connector.set_meal_plan(meal=dish, target_date=args.date, meal_type=args.moment)
        return MealSet(
            jour=MealDay(date=args.date, jour=WEEKDAYS_FR[args.date.weekday()], midi=updated.lunch, soir=updated.dinner),
            precedent=before,
            recette_connue=recipe is not None,
            undos=[MealUndo(date=args.date, moment=args.moment, before=before, after=dish)],
        )

    def get_recipe(self, args: GetRecipeArgs) -> RecipeView:
        recipe = self.connector.get_recipe_ingredients(args.nom)
        if recipe is None:
            raise MealsToolError(f"Recette « {args.nom} » introuvable dans le carnet de recettes.")
        return RecipeView(nom=recipe.name, ingredients=recipe.ingredients)

    # --- Annulation ---------------------------------------------------------------------------------------------

    @staticmethod
    def undo_targets(undo: MealsUndo) -> List[tuple]:
        """Cibles touchées : seule la dernière mutation d'une cible dans un lot doit correspondre à l'état actuel."""
        if isinstance(undo, MealUndo):
            return [("meal", undo.date.isoformat(), undo.moment)]
        if isinstance(undo, ShoppingCheckedUndo):
            names = undo.waiting + undo.week
        elif isinstance(undo, ShoppingRemovedUndo):
            names = [it.item for it in undo.items]
        else:
            names = undo.items
        return [("shopping", name.casefold()) for name in names]

    def check_undo(self, undo: MealsUndo, only: Optional[Collection[tuple]] = None) -> None:
        """Refuse l'annulation si l'état actuel ne correspond plus à celui laissé par l'agent (`only` : cibles à vérifier)."""
        def concerned(name: str) -> bool:
            return only is None or ("shopping", name.casefold()) in only

        if isinstance(undo, MealUndo):
            current = self._day_plan(undo.date)
            value = (current.midi if undo.moment == "midi" else current.soir) if current else None
            if (value or "") != undo.after:
                raise MealsToolError(
                    f"Annulation impossible : le repas du {undo.date:%d/%m} {undo.moment} a été modifié depuis "
                    f"(« {value or 'vide'} » au lieu de « {undo.after} »)."
                )
        elif isinstance(undo, ShoppingAddedUndo):
            present = [row.item for row in self.connector.get_waiting_list_rows()]
            gone = [name for name in undo.items if concerned(name) and name not in present]
            if gone:
                raise MealsToolError(f"Annulation impossible : {', '.join(gone)} n'est plus sur la liste de courses.")
        elif isinstance(undo, ShoppingCheckedUndo):
            waiting = {row.item: row.is_bought for row in self.connector.get_waiting_list_rows()}
            week = {it.name: it.checked for it in self.connector.get_shopping_list().get("current_week_items", [])}
            changed = [n for n in undo.waiting if concerned(n) and waiting.get(n) is not undo.checked]
            changed += [n for n in undo.week if concerned(n) and week.get(n) is not undo.checked]
            if changed:
                raise MealsToolError(f"Annulation impossible : {', '.join(changed)} a été modifié depuis.")

    def apply_undo(self, undo: MealsUndo) -> str:
        if isinstance(undo, MealUndo):
            self.connector.set_meal_plan(meal=undo.before or "", target_date=undo.date, meal_type=undo.moment)
            return f"repas du {WEEKDAYS_FR[undo.date.weekday()]} {undo.moment} rétabli ({undo.before or 'vide'})"
        if isinstance(undo, ShoppingAddedUndo):
            for name in undo.items:
                self.connector.remove_shopping_item(name)
            return f"ajout de {', '.join(undo.items)} aux courses annulé"
        if isinstance(undo, ShoppingCheckedUndo):
            self._set_checked(not undo.checked, undo.waiting, undo.week)
            return f"{', '.join(undo.waiting + undo.week)} {'décoché' if undo.checked else 'recoché'}"
        self.connector.restore_waiting_items(undo.items)
        return f"{', '.join(it.item for it in undo.items)} remis sur la liste de courses"

    # --- Interne ------------------------------------------------------------------------------------------------

    def _set_checked(self, checked: bool, waiting: List[str], week: List[str]) -> None:
        if waiting:
            if checked:
                self.connector.mark_shopping_items_bought(items=waiting)
            else:
                self.connector.unmark_shopping_items_bought(waiting)
        if week:
            if checked:
                self.connector.mark_current_week_items_bought(item_names=week)
            else:
                self.connector.unmark_current_week_items_bought(week)

    def _day_plan(self, day: date) -> Optional[MealDay]:
        try:
            plan = self.connector.get_meal_plan(target_date=day)
        except PlanningWorksheetNotFoundError as exc:
            raise MealsToolError(str(exc)) from exc
        except DayMealPlanNotFoundError:
            return None
        return MealDay(date=day, jour=WEEKDAYS_FR[day.weekday()], midi=plan.lunch, soir=plan.dinner)

    def _canonical_rayon(self, rayon: str, available: List[str]) -> str:
        for candidate in available:
            if self.connector.matches_item_name(rayon, candidate):
                return candidate
        raise MealsToolError(f"Rayon « {rayon} » inconnu. Rayons disponibles : {', '.join(available)}.")
