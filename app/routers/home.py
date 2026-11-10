"""Router de l'accueil de la PWA (refonte UX) : « Dernières actions »."""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.database import get_database_manager
from app.core.home.recent_actions import RecentActionsResponse, recent_actions
from app.core.security import verify_api_key

router = APIRouter(prefix="/api/v1/home", tags=["Accueil"], dependencies=[Depends(verify_api_key)])

# Fenêtre lue dans le journal : les lectures (« donne-moi la liste ») s'y intercalent entre les actions.
JOURNAL_WINDOW = 60


@router.get("/recent-actions", response_model=RecentActionsResponse, summary="Les 3 dernières actions faites par Otis")
async def get_recent_actions(
    session_id: Optional[str] = Query(None, description="Session de l'appareil : seule sa dernière action est annulable"),
    limit: int = Query(3, ge=1, le=10),
) -> RecentActionsResponse:
    logs = get_database_manager().get_conversation_logs(limit=JOURNAL_WINDOW, success=True)["items"]
    return RecentActionsResponse(items=recent_actions(logs, session_id=session_id, limit=limit))
