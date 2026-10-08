"""Router FastAPI pour l'analyse NLU et l'interaction conversationnelle universelle."""
import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, BackgroundTasks, File, UploadFile, Form, HTTPException, status

from app.core.security import verify_api_key
from app.core.models import (
    InteractionRequest,
    InteractionResponse,
    IntentType,
    ParsedIntent,
)
from app.core.intent_parser import IntentParser
from app.core.llm.nlu_service import get_nlu_service
from app.core.audio.phonetic_normalizer import normalize_phonetics
from app.core.audio.stt_service import get_stt_service
from app.core.dependencies import (
    get_meals_connector,
    get_sport_connector,
    get_sessions_store,
    get_database_manager,
)
from app.handlers.meals_handler import handle_meals_intent
from app.handlers.sport_handler import handle_sport_intent
from app.handlers.second_brain_handler import handle_second_brain_intent
from app.handlers.teach_handler import handle_teach_intent
from app.handlers.undo_handler import handle_undo_intent
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

    normalized_query = normalize_phonetics(request.query.strip())
    if not normalized_query:
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
    parsed = intent_parser.parse(normalized_query, context=session_ctx)

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
        handled = await handle_teach_intent(
            parsed=parsed,
            raw_query=request.query,
            session_ctx=session_ctx,
            data=data,
            session_id=session_id,
        )

    if handled is None:
        handled = await handle_undo_intent(
            parsed=parsed,
            raw_query=request.query,
            session_ctx=session_ctx,
            data=data,
            connector=connector,
            sport_connector=sport_connector,
        )

    if handled is None:
        handled = await handle_assistant_intent(
            parsed=parsed,
            raw_query=request.query,
            session_ctx=session_ctx,
            data=data,
        )

    # Mémorisation d'action réversible pour les ajouts de courses si l'action a réussi
    if parsed.intent == IntentType.ADD_SHOPPING_ITEM and handled is not None:
        raw_it = parsed.parameters.get("items") or parsed.parameters.get("item")
        if isinstance(raw_it, list):
            items_list = raw_it
        elif isinstance(raw_it, str):
            items_list = [raw_it]
        else:
            items_list = [request.query.strip()]
        session_ctx["last_undoable_action"] = {
            "type": "add_shopping_item",
            "items": items_list,
        }

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


@router.post(
    "/interact/audio",
    response_model=InteractionResponse,
    tags=["Interaction"],
    summary="Point d'entrée multimodal direct pour flux audio (WebM, WAV, OGG, MP3)",
)
async def interact_audio(
    audio_file: UploadFile = File(..., description="Fichier audio brut capté par le client"),
    session_id: Optional[str] = Form(None),
    background_tasks: BackgroundTasks = None,
):
    """Reçoit un fichier audio, effectue la transcription STT multimodale avec Gemini,
    applique la normalisation phonétique et exécute l'intention associée."""
    content_type = audio_file.content_type or ""
    allowed_prefixes = ("audio/", "video/webm", "video/ogg")
    if not (content_type.startswith("audio/") or content_type in allowed_prefixes):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Format de fichier non supporté ({content_type}). Veuillez fournir un fichier audio (WebM, WAV, OGG, MP3).",
        )

    audio_bytes = await audio_file.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le flux audio envoyé est vide.",
        )

    stt_service = get_stt_service()
    try:
        transcribed_text, _ = await stt_service.process_audio(
            audio_bytes=audio_bytes,
            mime_type=content_type,
            context={"session_id": session_id},
        )
    except Exception as exc:
        logger.error(f"Erreur lors du traitement STT audio : {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service de reconnaissance audio temporairement indisponible : {exc}",
        )

    req = InteractionRequest(
        query=transcribed_text,
        session_id=session_id,
        source="audio_direct",
    )
    resp = await interact(request=req, background_tasks=background_tasks)
    resp.transcribed_text = transcribed_text
    return resp


