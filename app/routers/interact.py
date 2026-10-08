"""Router FastAPI pour l'analyse NLU et l'interaction conversationnelle universelle."""
import logging
import time
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
    get_database_manager,
)
from app.handlers.meals_handler import handle_meals_intent
from app.handlers.sport_handler import handle_sport_intent
from app.handlers.second_brain_handler import handle_second_brain_intent
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
    4. Enregistre l'échange et les métriques de latence dans SQLite (conversation_logs)
    """
    start_time = time.perf_counter()
    session_id = request.session_id or request.source or "default"

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

    used_llm_model: Optional[str] = None

    # 1. Analyse locale déterministe
    parsed = intent_parser.parse(request.query, context=session_ctx)

    # 2. Si le modèle local ne comprend pas (UNKNOWN) : activation du cerveau LLM Gemini
    if parsed.intent == IntentType.UNKNOWN and nlu_service:
        llm_parsed = await nlu_service.parse(request.query, context=session_ctx)
        if llm_parsed.intent != IntentType.UNKNOWN or llm_parsed.conversational_reply:
            parsed = llm_parsed
            if hasattr(nlu_service, "gemini_client") and nlu_service.gemini_client:
                used_llm_model = getattr(nlu_service.gemini_client, "_resolved_model", None)

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
        handled = await handle_second_brain_intent(
            parsed=parsed,
            raw_query=request.query,
            session_ctx=session_ctx,
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

    is_success = parsed.intent != IntentType.UNKNOWN and "error" not in parsed.parameters
    latency_ms = (time.perf_counter() - start_time) * 1000
    error_trace = str(data.get("error")) if data.get("error") else None

    # 4. Traçabilité dans la base de données unifiée SQLite (conversation_logs)
    try:
        db = get_database_manager()
        log_id = db.log_conversation(
            session_id=session_id,
            raw_query=request.query,
            intent=parsed.intent.value,
            parameters=data,
            spoken_response=spoken,
            success=is_success,
            latency_ms=round(latency_ms, 2),
            llm_model=used_llm_model,
            error_trace=error_trace,
        )
        if isinstance(data, dict):
            data["log_id"] = log_id
    except Exception as log_exc:
        logger.warning(f"Impossible d'enregistrer l'échange dans conversation_logs : {log_exc}")

    return InteractionResponse(
        success=is_success,
        spoken_response=spoken,
        intent=parsed,
        data=data,
    )

