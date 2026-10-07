"""Router FastAPI pour l'analyse NLU et l'interaction conversationnelle universelle."""
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, BackgroundTasks

from app.core.security import verify_api_key
from app.core.models import (
    InteractionRequest,
    InteractionResponse,
    IntentType,
    ParsedIntent,
)
from app.core.intent_parser import IntentParser
from app.core.llm.nlu_service import get_nlu_service
from app.core.dependencies import (
    get_meals_connector,
    get_sport_connector,
    get_sessions_store,
)
from app.handlers.meals_handler import handle_meals_intent
from app.handlers.sport_handler import handle_sport_intent
from app.handlers.assistant_handler import handle_assistant_intent

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(verify_api_key)],
)

intent_parser = IntentParser()


@router.post(
    "/intent/parse",
    response_model=ParsedIntent,
    tags=["NLU"],
)
async def parse_intent(request: InteractionRequest):
    """Analyse la phrase en langage naturel et extrait l'intention et ses paramètres."""
    sessions = get_sessions_store()
    session_id = request.session_id or request.source or "default"
    session_ctx = sessions.setdefault(session_id, {})
    if request.context:
        session_ctx.update(request.context)
    return intent_parser.parse(request.query, context=session_ctx)


@router.post(
    "/interact",
    response_model=InteractionResponse,
    tags=["Interaction"],
)
async def interact(
    request: InteractionRequest,
    background_tasks: BackgroundTasks = None,
):
    """Point d'entrée universel pour les requêtes vocales ou textuelles.
    
    1. Parse l'intention (local puis LLM fallback)
    2. Route vers le handler spécialisé (Meals, Sport, Assistant)
    3. Formule une réponse parlée / textuelle et mémorise l'historique
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

    sessions = get_sessions_store()
    session_id = request.session_id or request.source or "default"
    session_ctx = sessions.setdefault(session_id, {})
    if request.context:
        session_ctx.update(request.context)

    connector = get_meals_connector()
    sport_connector = get_sport_connector()
    import sys
    main_mod = sys.modules.get("app.main")
    nlu_service = main_mod.get_nlu_service() if (main_mod and hasattr(main_mod, "get_nlu_service")) else get_nlu_service()

    # Enrichissement du contexte NLU avec la liste des rayons disponibles
    if connector and hasattr(connector, "get_available_rayons"):
        try:
            cand_rayons = connector.get_available_rayons()
            if isinstance(cand_rayons, list) and all(isinstance(r, str) for r in cand_rayons):
                session_ctx["available_rayons"] = cand_rayons
        except Exception:
            pass

    # 1. Analyse locale déterministe
    parsed = intent_parser.parse(request.query, context=session_ctx)

    # 2. Si le modèle local ne comprend pas (UNKNOWN) : activation du cerveau LLM Gemini
    if parsed.intent == IntentType.UNKNOWN and nlu_service:
        llm_parsed = await nlu_service.parse(request.query, context=session_ctx)
        if llm_parsed.intent != IntentType.UNKNOWN or llm_parsed.conversational_reply:
            parsed = llm_parsed

    data: Dict[str, Any] = dict(parsed.parameters)

    # 3. Aiguillage modulaire vers les handlers métier
    handled = await handle_meals_intent(
        parsed=parsed,
        raw_query=request.query,
        session_ctx=session_ctx,
        connector=connector,
        data=data,
    )

    if handled is None:
        handled = await handle_sport_intent(
            parsed=parsed,
            raw_query=request.query,
            session_ctx=session_ctx,
            sport_connector=sport_connector,
            data=data,
        )

    if handled is None:
        handled = await handle_assistant_intent(
            parsed=parsed,
            raw_query=request.query,
            session_ctx=session_ctx,
            data=data,
        )

    spoken, data = handled

    # Mémorisation du tour dans l'historique de la session pour la continuité conversationnelle
    hist = session_ctx.setdefault("history", [])
    hist.append({"role": "user", "text": request.query.strip()})
    hist.append({"role": "assistant", "text": spoken.strip()})
    if len(hist) > 6:
        session_ctx["history"] = hist[-6:]

    return InteractionResponse(
        success=parsed.intent != IntentType.UNKNOWN and "error" not in parsed.parameters,
        spoken_response=spoken,
        intent=parsed,
        data=data,
    )
