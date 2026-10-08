"""Router FastAPI pour les routes système, monitoring et préchauffage de cache."""
from fastapi import APIRouter

from app.config import settings
from app.core.dependencies import get_meals_connector

router = APIRouter(tags=["System"])


@router.get("/")
async def root():
    """Point d'entrée racine signalant l'état et la version du hub."""
    return {
        "app": settings.app_name,
        "version": "0.1.0",
        "status": "online",
        "docs": "/docs",
        "pwa": "/app",
    }


@router.get("/health")
async def health_check():
    """Vérification de santé de l'application."""
    return {
        "status": "healthy",
        "environment": settings.app_env,
        "debug": settings.debug,
    }


@router.get("/api/v1/llm/stats")
async def get_llm_stats():
    """Fournit les métriques et quotas de l'assistant LLM Gemini."""
    from app.core.llm.gemini_client import get_gemini_client
    client = get_gemini_client()
    return client.get_usage_stats()


@router.post("/api/v1/cache/warmup")
async def trigger_cache_warmup():
    """Déclenche le préchauffage en mémoire des catalogues de données."""
    connector = get_meals_connector()
    if not connector or not hasattr(connector, "warmup_cache"):
        return {"success": False, "message": "Connecteur non disponible", "stats": {}}
    stats = connector.warmup_cache()
    return {"success": True, "stats": stats}


# ============================================================================
# Journal Conversationnel & Audit (Phase 6)
# ============================================================================

from typing import Optional
from fastapi import Depends, HTTPException, status
from app.core.security import verify_api_key
from app.core.dependencies import get_database_manager
from app.core.models import (
    ConversationLogsListResponse,
    ConversationFeedbackCreate,
    ConversationFeedbackResponse,
)


@router.get(
    "/api/v1/system/conversation-logs",
    response_model=ConversationLogsListResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Consultation paginée du journal conversationnel et d'audit",
)
async def get_conversation_logs_endpoint(
    limit: int = 50,
    offset: int = 0,
    session_id: Optional[str] = None,
    success: Optional[bool] = None,
):
    """Retourne l'historique des interactions avec métriques de latence et intentions."""
    db = get_database_manager()
    return db.get_conversation_logs(
        limit=limit,
        offset=offset,
        session_id=session_id,
        success=success,
    )


@router.get(
    "/api/v1/system/conversation-logs/{log_id}",
    dependencies=[Depends(verify_api_key)],
    summary="Détail d'un log conversationnel précis",
)
async def get_conversation_log_detail_endpoint(log_id: int):
    """Retourne le détail d'un échange et ses feedbacks éventuels."""
    db = get_database_manager()
    log = db.get_conversation_log(log_id)
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Log {log_id} introuvable.",
        )
    feedbacks = db.get_feedbacks_for_log(log_id)
    log["feedbacks"] = feedbacks
    return log


@router.post(
    "/api/v1/system/conversation-logs/{log_id}/feedback",
    response_model=ConversationFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_api_key)],
    summary="Enregistrement d'un feedback sur un échange",
)
async def post_conversation_feedback_endpoint(
    log_id: int,
    feedback: ConversationFeedbackCreate,
):
    """Enregistre un retour utilisateur ou signalement d'erreur sur un échange."""
    db = get_database_manager()
    log = db.get_conversation_log(log_id)
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Log {log_id} introuvable.",
        )

    fb_id = db.add_feedback(
        log_id=log_id,
        feedback_type=feedback.feedback_type,
        user_note=feedback.user_note,
    )
    return ConversationFeedbackResponse(success=True, feedback_id=fb_id)

