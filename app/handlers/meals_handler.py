"""Handler dédié au traitement des intentions de repas et de gestion des courses."""
from datetime import date, timedelta
import logging
import re
from typing import Any, Dict, Optional, Tuple

from app.core.models import IntentType, ParsedIntent
from app.connectors.sheets.meals_connector import (
    MealsShoppingConnector,
    DayMealPlanNotFoundError,
    RecipeNotFoundError,
)
from app.core.date_resolver import parse_target_date
from app.core.llm.nlu_service import infer_rayon_with_llm

logger = logging.getLogger(__name__)


async def handle_meals_intent(
    parsed: ParsedIntent,
    raw_query: str,
    session_ctx: Dict[str, Any],
    connector: Optional[MealsShoppingConnector],
    data: Dict[str, Any],
) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Exécute l'intention si elle concerne le module repas ou courses.

    Retourne (spoken_response, data) si gérée, ou None si non applicable.
    """
    match parsed.intent:
        case IntentType.GET_MEAL_PLAN:
            period = parsed.parameters.get("period")
            target_date_str = parsed.parameters.get("target_date")
            day_name = parsed.parameters.get("day_name")

            if connector:
                try:
                    if period == "prochain" or (not period and not target_date_str):
                        plan, meal_type, label, dish = connector.get_next_meal_plan()
                        if dish and dish != "Rien de planifié":
                            spoken = f"D'après le planning des repas pour {label}, vous avez prévu : {dish}."
                            session_ctx["last_recipe"] = dish
                        else:
                            spoken = f"D'après le planning des repas pour {label}, aucun repas n'est encore programmé."
                        data["meal_plan"] = plan.model_dump()
                    else:
                        resolved_d = parse_target_date(target_date_str, period=period)
                        plan = connector.get_meal_plan(period=period, target_date=resolved_d)
                        today_d = date.today()
                        tomorrow_d = today_d + timedelta(days=1)
                        is_today = (resolved_d == today_d)
                        is_tomorrow = (resolved_d == tomorrow_d)

                        if is_today:
                            prefix = "Ce midi" if period == "midi" else ("Ce soir" if period == "soir" else "Aujourd'hui")
                        elif is_tomorrow:
                            prefix = "Demain midi" if period == "midi" else ("Demain soir" if period == "soir" else "Demain")
                        elif day_name and target_date_str and target_date_str.lower() not in ("today", "tomorrow", "demain", "aujourd'hui"):
                            day_label_base = f"{day_name} {target_date_str}"
                            prefix = f"{day_label_base} midi" if period == "midi" else (f"{day_label_base} soir" if period == "soir" else f"{day_label_base}")
                        elif day_name:
                            prefix = f"{day_name} midi" if period == "midi" else (f"{day_name} soir" if period == "soir" else f"{day_name}")
                        else:
                            date_display = resolved_d.strftime("%d/%m/%Y")
                            prefix = f"Pour le {date_display}"

                        if period == "midi":
                            dish = plan.lunch or "rien de planifié"
                            spoken = f"{prefix}, vous avez prévu : {dish}."
                            if plan.lunch:
                                session_ctx["last_recipe"] = plan.lunch
                        elif period == "soir":
                            dish = plan.dinner or "rien de planifié"
                            spoken = f"{prefix}, vous avez prévu : {dish}."
                            if plan.dinner:
                                session_ctx["last_recipe"] = plan.dinner
                        else:
                            if plan.lunch and plan.dinner:
                                spoken = f"{prefix}, vous avez prévu : à midi {plan.lunch}, et ce soir {plan.dinner}."
                                session_ctx["last_recipe"] = plan.dinner
                            elif plan.lunch:
                                spoken = f"{prefix}, vous avez prévu à midi : {plan.lunch} (rien pour le soir)."
                                session_ctx["last_recipe"] = plan.lunch
                            elif plan.dinner:
                                spoken = f"{prefix}, vous avez prévu pour ce soir : {plan.dinner} (rien pour le midi)."
                                session_ctx["last_recipe"] = plan.dinner
                            else:
                                spoken = f"{prefix}, aucun repas n'est encore programmé."

                        data["plan"] = plan.model_dump()
                        data["meal_plan"] = plan.model_dump()

                        if plan.lunch and connector and hasattr(connector, "get_recipe_ingredients"):
                            try:
                                rec_l = connector.get_recipe_ingredients(plan.lunch)
                                data["lunch_ingredients"] = rec_l.ingredients if rec_l else []
                            except Exception:
                                data["lunch_ingredients"] = []
                        if plan.dinner and connector and hasattr(connector, "get_recipe_ingredients"):
                            try:
                                rec_d = connector.get_recipe_ingredients(plan.dinner)
                                data["dinner_ingredients"] = rec_d.ingredients if rec_d else []
                            except Exception:
                                data["dinner_ingredients"] = []
                except DayMealPlanNotFoundError:
                    if is_today:
                        label_err = "ce midi" if period == "midi" else "ce soir"
                    elif is_tomorrow:
                        label_err = "demain midi" if period == "midi" else "demain soir"
                    elif day_name:
                        label_err = day_name
                    elif target_date_str and target_date_str.lower() not in ("today", "tomorrow", "demain", "aujourd'hui"):
                        label_err = f"le {resolved_d.strftime('%d/%m/%Y')}"
                    else:
                        label_err = period or "ce soir"
                    spoken = f"D'après le planning des repas pour {label_err}, aucun repas n'est encore programmé."
                except Exception as exc:
                    spoken = f"Impossible de récupérer le repas : {exc}"
            else:
                spoken = "D'après le planning des repas pour ce soir, vous avez prévu : Lasagnes maison et salade verte."
                session_ctx["last_recipe"] = "Lasagnes maison"
            return spoken, data

        case IntentType.GET_RECIPE_INGREDIENTS:
            recipe_name = parsed.parameters.get("recipe", "")
            if connector:
                recipe = connector.get_recipe_ingredients(recipe_name)
                if recipe:
                    spoken = f"Pour préparer {recipe.name}, il vous faut : {', '.join(recipe.ingredients)}."
                    data["recipe"] = recipe.model_dump()
                    session_ctx["last_recipe"] = recipe.name
                else:
                    spoken = f"Désolé, je n'ai pas trouvé la recette '{recipe_name}' dans vos carnets de recettes."
            else:
                spoken = f"Pour préparer {recipe_name}, il vous faut les ingrédients standard."
                session_ctx["last_recipe"] = recipe_name
            return spoken, data

        case IntentType.ADD_RECIPE_INGREDIENTS:
            if parsed.parameters.get("error") == "no_context_recipe":
                spoken = "Je ne sais pas de quelle recette vous parlez. Demandez-moi d'abord la recette ou les ingrédients d'un plat !"
            else:
                recipe_name = parsed.parameters.get("recipe", "")
                exclude = parsed.parameters.get("exclude")
                exclude_items = [exclude] if exclude else None
                if connector:
                    try:
                        recipe, added = connector.add_recipe_ingredients_to_shopping_list(
                            recipe_name=recipe_name,
                            exclude_items=exclude_items,
                        )
                        excl_suffix = f" (hors {exclude})" if exclude else ""
                        spoken = f"J'ai ajouté les ingrédients de {recipe.name}{excl_suffix} à votre liste de courses ({len(added)} article(s) en attente)."
                        data["recipe"] = recipe.model_dump()
                        data["added_items"] = [it.model_dump() for it in added]
                        session_ctx["last_recipe"] = recipe.name
                    except RecipeNotFoundError:
                        spoken = f"Impossible d'ajouter les ingrédients : la recette '{recipe_name}' est introuvable."
                    except Exception as exc:
                        spoken = f"Erreur lors de l'ajout des ingrédients de '{recipe_name}' : {exc}"
                else:
                    excl_suffix = f" (hors {exclude})" if exclude else ""
                    spoken = f"J'ai ajouté les ingrédients de {recipe_name}{excl_suffix} à votre liste de courses."
                    session_ctx["last_recipe"] = recipe_name
            return spoken, data

        case IntentType.SET_MEAL_PLAN:
            meal = parsed.parameters.get("meal", "")
            period = parsed.parameters.get("period", "soir")
            target_date_str = parsed.parameters.get("target_date")
            day_name = parsed.parameters.get("day_name")
            meal_type = "midi" if period == "midi" else "soir"

            resolved_target = parse_target_date(target_date_str, period=period)
            is_today = (resolved_target == date.today())
            is_tomorrow = (resolved_target == (date.today() + timedelta(days=1)))

            if is_today:
                target_label = "pour ce midi" if meal_type == "midi" else "pour ce soir"
            elif is_tomorrow:
                target_label = "pour demain midi" if meal_type == "midi" else "pour demain soir"
            elif day_name:
                target_label = f"pour {day_name}"
            else:
                target_label = f"le {resolved_target.strftime('%d/%m/%Y')}"

            recipe_exists = False
            meal_to_plan = meal
            if connector:
                try:
                    rec = connector.get_recipe_ingredients(meal)
                    if rec:
                        recipe_exists = True
                        meal_to_plan = rec.name
                except Exception:
                    recipe_exists = False

            if connector and not recipe_exists:
                session_ctx["pending_action"] = {
                    "type": "set_meal_plan",
                    "meal": meal,
                    "target_date": resolved_target.strftime("%d/%m/%Y"),
                    "day_name": day_name,
                    "meal_type": meal_type,
                    "period": period,
                }
                spoken = (
                    f"Attention, la recette '{meal}' n'est pas répertoriée dans votre carnet de recettes. "
                    f"Voulez-vous quand même la planifier {target_label} ?"
                )
                data["pending_action"] = session_ctx["pending_action"]
            else:
                if connector:
                    try:
                        updated_plan = connector.set_meal_plan(
                            meal=meal_to_plan,
                            target_date=resolved_target,
                            meal_type=meal_type,
                        )
                        spoken = f"C'est noté, j'ai planifié {meal_to_plan} {target_label}."
                        data["meal_plan"] = updated_plan.model_dump()
                        session_ctx["last_recipe"] = meal_to_plan
                    except Exception as exc:
                        spoken = f"Impossible d'enregistrer le repas : {exc}"
                else:
                    spoken = f"C'est noté, j'ai planifié {meal_to_plan} {target_label}."
                    session_ctx["last_recipe"] = meal_to_plan
            return spoken, data

        case IntentType.ADD_SHOPPING_ITEM:
            raw_items = parsed.parameters.get("items")
            if not raw_items:
                single = parsed.parameters.get("item", "l'article")
                raw_items = [single]

            if connector:
                try:
                    resolved_rayon, warning = (None, None)
                    if len(raw_items) == 1 and hasattr(connector, "resolve_rayon") and callable(getattr(connector, "resolve_rayon")):
                        clean_candidate = re.sub(
                            r"^(?:du|de\s+la|des|de\s+l[' ]|d[' ]|le|la|les|l[' ]|un[e]?)\s+",
                            "",
                            raw_items[0].strip(),
                            flags=re.IGNORECASE,
                        ).strip()
                        clean_candidate = (clean_candidate[0].upper() + clean_candidate[1:]) if clean_candidate else raw_items[0].strip()
                        try:
                            cand = connector.resolve_rayon(clean_candidate)
                            if isinstance(cand, (tuple, list)) and len(cand) == 2 and isinstance(cand[0], str):
                                resolved_rayon, warning = cand
                        except Exception:
                            resolved_rayon, warning = (None, None)

                        if warning and (resolved_rayon == "Divers" or "non répertorié" in warning.lower()):
                            explicit_rayon = parsed.parameters.get("rayon")
                            is_ambig = bool(parsed.parameters.get("is_ambiguous", False))
                            options = parsed.parameters.get("suggested_options")

                            if explicit_rayon and explicit_rayon.lower() not in ("divers", "unknown", "none") and not is_ambig:
                                added_item, _ = connector.add_shopping_item(clean_candidate, rayon=explicit_rayon)
                                spoken = f"C'est noté, j'ai ajouté {added_item.item} au rayon {explicit_rayon} dans votre liste de courses."
                                data["items"] = [added_item.model_dump()]
                                data["item"] = added_item.model_dump()
                                return spoken, data

                            if is_ambig and options and isinstance(options, list) and len(options) >= 1:
                                suggested = options
                                session_ctx["pending_action"] = {
                                    "type": "clarify_shopping_rayon",
                                    "item": clean_candidate,
                                    "raw_items": raw_items,
                                    "suggested_rayons": suggested,
                                }
                                sug_str = f"en {suggested[0]} ou en {suggested[1]}" if len(suggested) >= 2 else f"au rayon {suggested[0]}"
                                spoken = (
                                    parsed.conversational_reply
                                    or f"Je n'ai pas de rayon certain pour '{clean_candidate}'. Veux-tu que je le range {sug_str} ?"
                                )
                                data["pending_action"] = session_ctx["pending_action"]
                                data["suggested_rayons"] = suggested
                                return spoken, data

                            raw_avail = connector.get_available_rayons() if hasattr(connector, "get_available_rayons") else []
                            avail = [r for r in raw_avail if isinstance(r, str)] if isinstance(raw_avail, list) else []
                            inferred_rayon, options = await infer_rayon_with_llm(clean_candidate, avail)
                            if options is None and inferred_rayon and inferred_rayon.lower() != "divers":
                                added_item, _ = connector.add_shopping_item(clean_candidate, rayon=inferred_rayon)
                                spoken = f"C'est noté, j'ai ajouté {added_item.item} au rayon {inferred_rayon} dans votre liste de courses."
                                data["items"] = [added_item.model_dump()]
                                data["item"] = added_item.model_dump()
                                return spoken, data

                            suggested = options if options else (connector.suggest_rayons_for_item(clean_candidate) if hasattr(connector, "suggest_rayons_for_item") else ["Entretien", "Épicerie"])
                            session_ctx["pending_action"] = {
                                "type": "clarify_shopping_rayon",
                                "item": clean_candidate,
                                "raw_items": raw_items,
                                "suggested_rayons": suggested,
                            }
                            sug_str = f"en {suggested[0]} ou en {suggested[1]}" if len(suggested) >= 2 else f"au rayon {suggested[0]}"
                            spoken = (
                                f"Je n'ai pas de rayon certain pour '{clean_candidate}'. "
                                f"Veux-tu que je le range {sug_str} ?"
                            )
                            data["pending_action"] = session_ctx["pending_action"]
                            data["suggested_rayons"] = suggested
                            return spoken, data

                    res = None
                    if hasattr(connector, "add_shopping_items"):
                        try:
                            candidate = connector.add_shopping_items(raw_items)
                            if isinstance(candidate, (tuple, list)) and len(candidate) == 2 and isinstance(candidate[0], list):
                                res = candidate
                        except Exception:
                            res = None

                    if res is not None:
                        added_items, warnings = res
                    else:
                        added_items = []
                        warnings = []
                        for it in raw_items:
                            ai, w = connector.add_shopping_item(it)
                            added_items.append(ai)
                            if w:
                                warnings.append(w)

                    if len(added_items) == 1:
                        spoken = f"C'est noté, j'ai ajouté {added_items[0].item} à votre liste de courses."
                    else:
                        names = [it.item for it in added_items]
                        spoken = f"C'est noté, j'ai ajouté {len(added_items)} article(s) à votre liste de courses : {', '.join(names)}."

                    if warnings:
                        spoken += f" ({'; '.join(warnings)})"

                    data["items"] = [it.model_dump() for it in added_items]
                    data["item"] = added_items[0].model_dump() if added_items else {}
                except Exception as exc:
                    spoken = f"Impossible d'ajouter à la liste de courses : {exc}"
            else:
                if len(raw_items) == 1:
                    spoken = f"C'est noté, j'ai ajouté {raw_items[0]} à votre liste de courses."
                else:
                    spoken = f"C'est noté, j'ai ajouté {len(raw_items)} article(s) à votre liste de courses : {', '.join(raw_items)}."
            return spoken, data

        case IntentType.GET_SHOPPING_LIST:
            filter_mode = parsed.parameters.get("filter")
            req_rayon = parsed.parameters.get("rayon")
            status = parsed.parameters.get("status", "remaining")

            if req_rayon:
                session_ctx["last_rayon"] = req_rayon
                session_ctx["last_intent"] = IntentType.GET_SHOPPING_LIST

            if connector:
                try:
                    shopping = connector.get_shopping_list()
                    waiting_items = [it for it in shopping.get("waiting_list", []) if not it.is_bought]
                    current_items = shopping.get("current_week_items", [])

                    if filter_mode == "waiting_list":
                        waiting_names = [it.item for it in waiting_items]
                        if waiting_names:
                            spoken = f"Voici les articles sur votre liste d'attente : {', '.join(waiting_names)}."
                        else:
                            spoken = "Votre liste d'attente est actuellement vide."
                    elif filter_mode == "current_week":
                        if req_rayon:
                            rayon_items = [
                                it for it in current_items
                                if it.rayon and (it.rayon.lower() == req_rayon.lower() or req_rayon.lower() in it.rayon.lower())
                            ]
                            if not rayon_items:
                                spoken = f"Vous n'avez aucun article prévu au rayon {req_rayon} cette semaine."
                            else:
                                rem = [it.name for it in rayon_items if not it.checked]
                                chk = [it.name for it in rayon_items if it.checked]
                                if status == "checked":
                                    if chk:
                                        spoken = f"Au rayon {req_rayon}, vous avez déjà coché : {', '.join(chk)}."
                                    else:
                                        spoken = f"Au rayon {req_rayon}, aucun article n'a encore été coché."
                                else:
                                    if rem:
                                        chk_suffix = f" ({len(chk)} article(s) déjà coché(s))" if chk else ""
                                        spoken = f"Au rayon {req_rayon}, il vous reste à acheter : {', '.join(rem)}{chk_suffix}."
                                    else:
                                        spoken = f"Au rayon {req_rayon}, tous les articles sont déjà cochés !"
                        else:
                            rem = [it for it in current_items if not it.checked]
                            chk = [it for it in current_items if it.checked]
                            if status == "checked":
                                if chk:
                                    spoken = f"Voici les articles déjà cochés cette semaine : {', '.join(it.name for it in chk)}."
                                else:
                                    spoken = "Aucun article n'a encore été coché cette semaine."
                            else:
                                if rem:
                                    chk_suffix = f" ({len(chk)} article(s) déjà coché(s))" if chk else ""
                                    spoken = f"Dans votre liste de la semaine, il vous reste {len(rem)} article(s) à acheter : {', '.join(it.name for it in rem)}{chk_suffix}."
                                else:
                                    spoken = "Tous les articles de la semaine sont déjà cochés, vos courses sont terminées !"
                    else:
                        all_names = [it.item for it in waiting_items] + [it.name for it in current_items if not it.checked]
                        if all_names:
                            spoken = f"Voici les articles sur votre liste de courses : {', '.join(all_names)}."
                        else:
                            spoken = "Votre liste de courses est actuellement vide."
                    rayons_order = shopping.get("rayons_order", {})
                    data["shopping_list"] = {
                        "waiting_list": [it.model_dump() for it in shopping.get("waiting_list", [])],
                        "current_week_items": [it.model_dump() for it in current_items],
                        "rayons_order": rayons_order,
                    }
                    data["waiting_list"] = [it.model_dump() for it in shopping.get("waiting_list", [])]
                    data["current_week_items"] = [it.model_dump() for it in current_items]
                    data["rayons_order"] = rayons_order
                except Exception as exc:
                    spoken = f"Impossible de lire la liste de courses : {exc}"
            else:
                if filter_mode == "waiting_list":
                    spoken = "Voici les articles sur votre liste d'attente : Café bio, Pommes."
                elif filter_mode == "current_week":
                    if req_rayon:
                        if status == "checked":
                            spoken = f"Au rayon {req_rayon}, vous avez déjà coché : Pommes."
                        else:
                            spoken = f"Au rayon {req_rayon}, il vous reste à acheter : Bananes (1 article(s) déjà coché(s))."
                    else:
                        if status == "checked":
                            spoken = "Voici les articles déjà cochés cette semaine : Pommes."
                        else:
                            spoken = "Dans votre liste de la semaine, il vous reste 2 articles à acheter : Bananes, Lait (1 article(s) déjà coché(s))."
                else:
                    spoken = "Voici les articles sur votre liste de courses : Pain, Pommes, Lait d'avoine."
            return spoken, data

        case IntentType.MARK_SHOPPING_BOUGHT:
            is_all = parsed.parameters.get("all") is True
            items_str = parsed.parameters.get("items", "")
            items_list = [i.strip() for i in re.split(r",|\bet\b", items_str) if i.strip()]
            if connector:
                try:
                    if is_all:
                        marked = connector.mark_shopping_items_bought(mark_all=True)
                        spoken = f"C'est noté, j'ai coché tous les articles de la liste d'attente comme achetés ({len(marked)} article(s) mis à jour)."
                    else:
                        marked = connector.mark_shopping_items_bought(items=items_list)
                        spoken = f"C'est noté, j'ai coché comme acheté(s) : {', '.join(marked) if marked else items_str}."
                    data["marked"] = marked
                except Exception as exc:
                    spoken = f"Impossible de mettre à jour les achats : {exc}"
            else:
                if is_all:
                    spoken = "C'est noté, j'ai coché tous les articles comme achetés."
                else:
                    spoken = f"C'est noté, j'ai coché comme acheté(s) : {items_str}."
            return spoken, data

        case IntentType.CLEAR_SHOPPING_LIST:
            if connector:
                try:
                    count = connector.clear_shopping_list(only_bought=True)
                    spoken = f"La liste de courses a été nettoyée ({count} article(s) acheté(s) supprimé(s))."
                    data["deleted_count"] = count
                except Exception as exc:
                    spoken = f"Impossible de nettoyer la liste de courses : {exc}"
            else:
                spoken = "La liste de courses a été nettoyée."
            return spoken, data

        case IntentType.CHECK_SHOPPING_COMPLETION:
            if connector:
                try:
                    shopping = connector.get_shopping_list()
                    waiting_items = [it for it in shopping.get("waiting_list", []) if not it.is_bought]
                    current_items = [it for it in shopping.get("current_week_items", []) if not it.checked]

                    remaining = [it.item for it in waiting_items] + [it.name for it in current_items]
                    if remaining:
                        spoken = f"Attention, il vous reste encore {len(remaining)} article(s) à prendre : {', '.join(remaining)}."
                        completed = False
                    else:
                        spoken = "Félicitations, vous avez tout pris ! Votre liste de courses est complète."
                        completed = True

                    data["completed"] = completed
                    data["remaining_items"] = remaining
                except Exception as exc:
                    spoken = f"Impossible de vérifier la liste de courses : {exc}"
                    data["completed"] = False
                    data["remaining_items"] = []
            else:
                spoken = "Félicitations, vous avez tout pris ! Votre liste de courses est complète."
                data["completed"] = True
                data["remaining_items"] = []
            return spoken, data

        case IntentType.CHOOSE_RAYON:
            pending = session_ctx.pop("pending_action", None)
            if pending and pending.get("type") == "clarify_shopping_rayon":
                item = pending.get("item", "l'article")
                chosen_rayon = parsed.parameters.get("rayon", "Divers")
                if connector:
                    try:
                        added_item, _ = connector.add_shopping_item(item, rayon=chosen_rayon)
                        spoken = f"C'est noté, j'ai ajouté {added_item.item} au rayon {chosen_rayon} dans votre liste de courses."
                        data["item"] = added_item.model_dump()
                        data["items"] = [added_item.model_dump()]
                    except Exception as exc:
                        spoken = f"Impossible d'ajouter à la liste de courses : {exc}"
                else:
                    spoken = f"C'est noté, j'ai ajouté {item} au rayon {chosen_rayon} dans votre liste de courses."
            else:
                spoken = "C'est noté !"
            return spoken, data

        case IntentType.CONFIRM:
            pending = session_ctx.get("pending_action")
            if pending and pending.get("type") == "set_meal_plan":
                session_ctx.pop("pending_action", None)
                meal = pending["meal"]
                target_date_str = pending.get("target_date")
                meal_type = pending.get("meal_type", "soir")
                day_name = pending.get("day_name")
                period = pending.get("period", "soir")
                target = parse_target_date(target_date_str, period=period)
                is_today = (target == date.today())
                is_tomorrow = (target == (date.today() + timedelta(days=1)))
                if is_today:
                    target_label = "pour ce midi" if meal_type == "midi" else "pour ce soir"
                elif is_tomorrow:
                    target_label = "pour demain midi" if meal_type == "midi" else "pour demain soir"
                elif day_name:
                    target_label = f"pour {day_name}"
                else:
                    target_label = f"le {target.strftime('%d/%m/%Y')}"

                if connector:
                    try:
                        updated_plan = connector.set_meal_plan(
                            meal=meal,
                            target_date=target,
                            meal_type=meal_type,
                        )
                        spoken = f"C'est confirmé, j'ai ajouté '{meal}' {target_label} au planning."
                        data["meal_plan"] = updated_plan.model_dump()
                        session_ctx["last_recipe"] = meal
                    except Exception as exc:
                        spoken = f"Impossible d'enregistrer le repas : {exc}"
                else:
                    spoken = f"C'est confirmé, j'ai ajouté '{meal}' {target_label} au planning."
                    session_ctx["last_recipe"] = meal
                return spoken, data

            elif pending and pending.get("type") == "clarify_shopping_rayon":
                session_ctx.pop("pending_action", None)
                item = pending.get("item", "l'article")
                suggested = pending.get("suggested_rayons", ["Divers"])
                default_rayon = suggested[0] if suggested else "Divers"
                if connector:
                    try:
                        added_item, _ = connector.add_shopping_item(item, rayon=default_rayon)
                        spoken = f"C'est noté, j'ai ajouté {added_item.item} au rayon {default_rayon} dans votre liste de courses."
                        data["item"] = added_item.model_dump()
                        data["items"] = [added_item.model_dump()]
                    except Exception as exc:
                        spoken = f"Impossible d'ajouter à la liste de courses : {exc}"
                else:
                    spoken = f"C'est noté, j'ai ajouté {item} au rayon {default_rayon} dans votre liste de courses."
                return spoken, data
            return None

        case IntentType.CANCEL:
            pending = session_ctx.get("pending_action")
            if pending and pending.get("type") == "clarify_shopping_rayon":
                session_ctx.pop("pending_action", None)
                item = pending.get("item", "l'article")
                spoken = f"Très bien, j'ai annulé l'ajout de {item}."
                return spoken, data
            return None

        case _:
            return None
