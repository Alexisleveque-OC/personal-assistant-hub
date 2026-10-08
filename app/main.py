"""Point d'entrée principal de l'application FastAPI Personal Assistant Hub.

Ce module orchestre l'application, configure les middlewares, le cycle de vie
(préchauffage asynchrone des caches au démarrage) et assemble les sous-routeurs modulaires.
"""
import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

# Import des routeurs modulaires
from app.routers.system import router as system_router
from app.routers.interact import (
    router as interact_router,
    interact,
    parse_intent,
    intent_parser,
)
from app.routers.mobile import router as mobile_router, mobile_interact
from app.routers.meals import router as meals_router
from app.routers.sport import router as sport_router
from app.routers.strava import router as strava_router
from app.routers.pwa import router as pwa_router, mount_static_files

# Réexports rétrocompatibles des dépendances et singletons pour les tests
from app.core.dependencies import (
    get_meals_connector,
    set_meals_connector,
    get_sport_connector,
    set_sport_connector,
    get_sport_connector_error,
    get_sessions_store,
    clear_sessions,
    _SESSIONS,
    get_database_manager,
    set_database_manager,
)
from app.core.database import DatabaseManager
from app.core.llm.nlu_service import (
    GeminiNLUService,
    get_nlu_service,
    set_nlu_service,
    infer_rayon_with_llm,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cycle de vie FastAPI : initialise SQLite et préchauffe les caches mémoire en arrière-plan."""
    try:
        get_database_manager().init_db()
    except Exception as exc:
        logger.warning(f"Impossible d'initialiser la base SQLite : {exc}")

    connector = get_meals_connector()
    if connector and hasattr(connector, "warmup_cache"):
        try:
            asyncio.create_task(asyncio.to_thread(connector.warmup_cache))
        except Exception as exc:
            logger.warning(f"Impossible de lancer le préchauffage initial du cache repas : {exc}")

    sport_conn = get_sport_connector()
    if sport_conn and hasattr(sport_conn, "warmup_cache"):
        try:
            asyncio.create_task(asyncio.to_thread(sport_conn.warmup_cache))
        except Exception as exc:
            logger.warning(f"Impossible de lancer le préchauffage initial du cache sport : {exc}")
    yield



app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Hub d'assistant personnel connecté à Google Sheets, Google Tasks, Gmail et Domotique.",
    lifespan=lifespan,
)

# CORS pour autoriser l'accès depuis une PWA, un widget ou un frontend local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Enregistrement des sous-routeurs métier découplés
app.include_router(system_router)
app.include_router(interact_router)
app.include_router(mobile_router)
app.include_router(meals_router)
app.include_router(sport_router)
app.include_router(strava_router)
app.include_router(pwa_router)

# Montage des fichiers statiques PWA
mount_static_files(app)
