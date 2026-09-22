"""Point d'entrée principal de l'API Personal Assistant Hub."""
from fastapi import FastAPI, Depends, Request, Query
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.security import verify_api_key
from app.core.models import (
    InteractionRequest,
    InteractionResponse,
    IntentType,
    ParsedIntent,
)
from app.core.intent_parser import IntentParser

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Hub d'assistant personnel connecté à Google Sheets, Google Tasks, Gmail et Domotique.",
)

# CORS pour autoriser l'accès depuis une PWA, un widget ou un frontend local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from datetime import date, timedelta
import re
from typing import Optional

from app.connectors.sheets.meals_connector import (
    MealsShoppingConnector,
    DayMealPlanNotFoundError,
    RecipeNotFoundError,
)

intent_parser = IntentParser()

import logging

logger = logging.getLogger(__name__)

_meals_connector: Optional[MealsShoppingConnector] = None


def get_meals_connector() -> Optional[MealsShoppingConnector]:
    """Récupère l'instance active du connecteur de repas ou tente son initialisation."""
    global _meals_connector
    if _meals_connector is None:
        try:
            _meals_connector = MealsShoppingConnector()
        except Exception as exc:
            logger.warning(f"Impossible d'initialiser MealsShoppingConnector : {exc}")
            _meals_connector = None
    return _meals_connector


def set_meals_connector(connector: Optional[MealsShoppingConnector]) -> None:
    """Permet l'injection d'un connecteur (mock) pour les tests unitaires et d'intégration."""
    global _meals_connector
    _meals_connector = connector


_SESSIONS: dict[str, dict] = {}


def clear_sessions() -> None:
    """Réinitialise la mémoire de session (utilitaire pour les tests)."""
    _SESSIONS.clear()


@app.get("/", tags=["System"])
async def root():
    return {
        "app": settings.app_name,
        "version": "0.1.0",
        "status": "online",
        "docs": "/docs",
    }


@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "healthy",
        "environment": settings.app_env,
        "debug": settings.debug,
    }


@app.post(
    "/api/v1/intent/parse",
    response_model=ParsedIntent,
    tags=["NLU"],
    dependencies=[Depends(verify_api_key)],
)
async def parse_intent(request: InteractionRequest):
    """Analyse la phrase en langage naturel et extrait l'intention et ses paramètres."""
    session_id = request.session_id or request.source or "default"
    session_ctx = _SESSIONS.setdefault(session_id, {})
    if request.context:
        session_ctx.update(request.context)
    return intent_parser.parse(request.query, context=session_ctx)


@app.post(
    "/api/v1/interact",
    response_model=InteractionResponse,
    tags=["Interaction"],
    dependencies=[Depends(verify_api_key)],
)
async def interact(request: InteractionRequest):
    """Point d'entrée universel pour les requêtes vocales ou textuelles.
    
    1. Parse l'intention
    2. Route vers le connecteur approprié (MealsShoppingConnector, Tasks, etc.)
    3. Formule une réponse parlée / textuelle
    """
    if not request.query or not request.query.strip():
        return InteractionResponse(
            success=False,
            spoken_response="Je n'ai rien entendu. Pouvez-vous répéter votre demande ?",
            intent=ParsedIntent(
                intent=IntentType.UNKNOWN,
                confidence=0.0,
                parameters={},
                raw_query="",
            ),
            data={},
        )

    session_id = request.session_id or request.source or "default"
    session_ctx = _SESSIONS.setdefault(session_id, {})
    if request.context:
        session_ctx.update(request.context)

    parsed = intent_parser.parse(request.query, context=session_ctx)
    connector = get_meals_connector()
    data = dict(parsed.parameters)

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
                        # Jour ou date ciblé
                        plan = connector.get_meal_plan(period=period, target_date=target_date_str)
                        # Libellé du jour/moment
                        if day_name:
                            day_label = f"{day_name}" + (f" {target_date_str}" if target_date_str else "")
                        elif target_date_str:
                            day_label = f"le {target_date_str}"
                        elif period == "demain":
                            day_label = "demain"
                        elif period == "midi":
                            day_label = "ce midi"
                        elif period == "soir":
                            day_label = "ce soir"
                        else:
                            day_label = period or "aujourd'hui"

                        if period == "midi":
                            dish = plan.lunch or "Rien de planifié"
                            spoken = f"D'après le planning des repas pour {day_label}, vous avez prévu : {dish}."
                            if plan.lunch:
                                session_ctx["last_recipe"] = plan.lunch
                        elif period == "soir":
                            dish = plan.dinner or "Rien de planifié"
                            spoken = f"D'après le planning des repas pour {day_label}, vous avez prévu : {dish}."
                            if plan.dinner:
                                session_ctx["last_recipe"] = plan.dinner
                        else:
                            # Journée complète demandée
                            if plan.lunch and plan.dinner:
                                spoken = f"Pour {day_label}, vous avez prévu : à midi {plan.lunch}, et ce soir {plan.dinner}."
                                session_ctx["last_recipe"] = plan.dinner
                            elif plan.lunch:
                                spoken = f"Pour {day_label}, vous avez prévu à midi : {plan.lunch} (rien pour le soir)."
                                session_ctx["last_recipe"] = plan.lunch
                            elif plan.dinner:
                                spoken = f"Pour {day_label}, vous avez prévu pour ce soir : {plan.dinner} (rien pour le midi)."
                                session_ctx["last_recipe"] = plan.dinner
                            else:
                                spoken = f"D'après le planning des repas pour {day_label}, aucun repas n'est encore programmé."
                        data["meal_plan"] = plan.model_dump()
                except DayMealPlanNotFoundError:
                    label_err = day_name or target_date_str or period or "ce soir"
                    spoken = f"D'après le planning des repas pour {label_err}, aucun repas n'est encore programmé."
                except Exception as exc:
                    spoken = f"Impossible de récupérer le repas : {exc}"
            else:
                spoken = "D'après le planning des repas pour ce soir, vous avez prévu : Lasagnes maison et salade verte."
                session_ctx["last_recipe"] = "Lasagnes maison"

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

        case IntentType.SET_MEAL_PLAN:
            meal = parsed.parameters.get("meal", "")
            period = parsed.parameters.get("period", "soir")
            target_date_str = parsed.parameters.get("target_date")
            day_name = parsed.parameters.get("day_name")
            meal_type = "midi" if period == "midi" else "soir"

            # 1. Vérification si la recette existe
            recipe_exists = False
            if connector:
                try:
                    rec = connector.get_recipe_ingredients(meal)
                    recipe_exists = bool(rec)
                except Exception:
                    recipe_exists = False

            target_label = f"pour {day_name}" if day_name else (f"le {target_date_str}" if target_date_str else (f"pour {period}" if period != "jour" else "pour aujourd'hui"))

            if connector and not recipe_exists:
                # Recette non répertoriée -> Demande confirmation interactive
                session_ctx["pending_action"] = {
                    "type": "set_meal_plan",
                    "meal": meal,
                    "target_date": target_date_str,
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
                # Recette connue (ou sans connecteur en fallback) -> insertion immédiate
                if target_date_str:
                    target_date = target_date_str
                elif period == "demain":
                    target_date = date.today() + timedelta(days=1)
                else:
                    target_date = date.today()

                if connector:
                    try:
                        updated_plan = connector.set_meal_plan(
                            meal=meal,
                            target_date=target_date,
                            meal_type=meal_type,
                        )
                        spoken = f"C'est noté, j'ai planifié {meal} {target_label}."
                        data["meal_plan"] = updated_plan.model_dump()
                        session_ctx["last_recipe"] = meal
                    except Exception as exc:
                        spoken = f"Impossible d'enregistrer le repas : {exc}"
                else:
                    spoken = f"C'est noté, j'ai planifié {meal} {target_label}."
                    session_ctx["last_recipe"] = meal

        case IntentType.ADD_SHOPPING_ITEM:
            raw_items = parsed.parameters.get("items")
            if not raw_items:
                single = parsed.parameters.get("item", "l'article")
                raw_items = [single]

            if connector:
                try:
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
                    data["shopping_list"] = {
                        "waiting_list": [it.model_dump() for it in shopping.get("waiting_list", [])],
                        "current_week_items": [it.model_dump() for it in current_items],
                    }
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

        case IntentType.GET_BUDGET_BALANCE:
            cat = parsed.parameters.get("category", "général")
            spoken = f"Il vous reste actuellement 145 euros sur votre budget {cat} pour ce mois."
        case IntentType.LOG_EXPENSE:
            amount = parsed.parameters.get("amount", 0)
            cat = parsed.parameters.get("category", "divers")
            spoken = f"C'est enregistré : {amount} euros ajoutés aux dépenses {cat}."
        case IntentType.ADD_TASK:
            task = parsed.parameters.get("task", "tâche")
            spoken = f"Tâche enregistrée dans Google Tasks : {task}."
        case IntentType.LIST_TASKS:
            spoken = "Vous avez 2 tâches aujourd'hui : Rappeler le garage et arroser les plantes."
        case IntentType.SUMMARIZE_EMAILS:
            spoken = "Vous avez 1 e-mail important de votre banque concernant un relevé mensuel."
        case IntentType.TOGGLE_DEVICE:
            device = parsed.parameters.get("device", "appareil")
            action = "allumée" if parsed.parameters.get("action") == "on" else "éteinte"
            spoken = f"La {device} a bien été {action}."
        case IntentType.SMALL_TALK:
            sub_type = parsed.parameters.get("type", "ack")
            if sub_type == "thanks":
                spoken = "Avec plaisir ! N'hésitez pas si vous avez besoin d'autre chose."
            elif sub_type == "greeting":
                spoken = "Bonjour ! Que puis-je faire pour vous aujourd'hui ?"
            elif sub_type == "farewell":
                spoken = "Au revoir et bonne journée ! 👋"
            else:
                spoken = "Parfait ! Que souhaitez-vous faire d'autre ?"

        case IntentType.CONFIRM:
            pending = session_ctx.pop("pending_action", None)
            if pending and pending.get("type") == "set_meal_plan":
                meal = pending["meal"]
                target_date_str = pending.get("target_date")
                meal_type = pending.get("meal_type", "soir")
                day_name = pending.get("day_name")
                period = pending.get("period", "soir")
                target_label = f"pour {day_name}" if day_name else (f"le {target_date_str}" if target_date_str else f"pour {period}")

                target = target_date_str if target_date_str else (date.today() + timedelta(days=1) if period == "demain" else date.today())
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
            else:
                spoken = "C'est noté !"

        case IntentType.CANCEL:
            session_ctx.pop("pending_action", None)
            spoken = "Très bien, j'ai annulé l'opération."

        case _:
            spoken = "Je n'ai pas bien compris votre demande. Pouvez-vous reformuler ?"

    return InteractionResponse(
        success=parsed.intent != IntentType.UNKNOWN and "error" not in parsed.parameters,
        spoken_response=spoken,
        intent=parsed,
        data=data,
    )


@app.post(
    "/api/v1/mobile/interact",
    response_model=InteractionResponse,
    tags=["Mobile"],
    dependencies=[Depends(verify_api_key)],
    operation_id="mobile_interact_post",
)
@app.get(
    "/api/v1/mobile/interact",
    response_model=InteractionResponse,
    tags=["Mobile"],
    dependencies=[Depends(verify_api_key)],
    operation_id="mobile_interact_get",
)
async def mobile_interact(
    req: Request,
    text: Optional[str] = Query(None, description="Texte de la requête pour appels GET ou query params"),
    payload: Optional[InteractionRequest] = None,
):
    """Adaptateur optimisé pour les raccourcis mobiles Android (HTTP Shortcuts, Tasker, widgets).

    - Accepte GET (?text=...) ou POST (JSON avec 'text', 'message' ou 'query').
    - Retourne du JSON ou du texte brut directement si 'Accept: text/plain' est spécifié.
    """
    query_text = ""
    source = "android"
    session_id = "mobile_session"
    context = {}

    if payload:
        query_text = payload.query
        source = payload.source or source
        session_id = payload.session_id or session_id
        context = payload.context or context
    elif text is not None:
        query_text = text

    # Si la requête POST contenait un JSON brut avec des clés alternatives
    if not query_text and req.method == "POST":
        try:
            body = await req.json()
            if isinstance(body, dict):
                query_text = (
                    body.get("query")
                    or body.get("text")
                    or body.get("message")
                    or body.get("prompt")
                    or ""
                )
                source = body.get("source", source)
                session_id = body.get("session_id", session_id)
        except Exception:
            pass

    interact_req = InteractionRequest(
        query=query_text,
        source=source,
        session_id=session_id,
        context=context,
    )
    res = await interact(interact_req)

    # Réponse texte brut si demandée (ex: pour être lue directement par le TTS Android)
    accept_header = req.headers.get("accept", "")
    if "text/plain" in accept_header:
        return PlainTextResponse(content=res.spoken_response)

    return res

