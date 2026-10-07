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
