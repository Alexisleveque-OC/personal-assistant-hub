"""Router de l'accueil de la PWA (refonte UX) : « Dernières actions » et leur annulation."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.agent.errors import AgentUnavailableError
from app.core.agent.factory import build_undo_service
from app.core.agent.undo import UndoError
from app.core.database import get_database_manager
from app.core.dependencies import get_meals_connector, get_sport_connector
from app.core.home.recent_actions import RecentActionsResponse, action_label, recent_actions, undo_batch_id
from app.core.security import verify_api_key

router = APIRouter(prefix="/api/v1/home", tags=["Accueil"], dependencies=[Depends(verify_api_key)])

# Fenêtre lue dans le journal : les lectures (« donne-moi la liste ») s'y intercalent entre les actions.
JOURNAL_WINDOW = 60
# Annulation faite depuis la liste : tracée dans le journal des conversations, jamais affichée comme une action.
UNDO_RECENT_ACTION_INTENT = "undo_recent_action"


class RecentActionUndoResponse(BaseModel):
    spoken_response: str
    restored: List[str]
    sport_session_ids: List[int]


@router.get("/recent-actions", response_model=RecentActionsResponse, summary="Les 3 dernières actions faites par Otis")
async def get_recent_actions(
    session_id: Optional[str] = Query(None, description="Session de l'appareil : seules ses actions sont annulables"),
    limit: int = Query(3, ge=1, le=10),
) -> RecentActionsResponse:
    db = get_database_manager()
    logs = db.get_conversation_logs(limit=JOURNAL_WINDOW, success=True)["items"]
    batch_ids = [batch_id for batch_id in map(undo_batch_id, logs) if batch_id is not None]
    batches = db.get_agent_undo_batches(batch_ids)
    return RecentActionsResponse(items=recent_actions(logs, session_id=session_id, limit=limit, batches=batches))


@router.post(
    "/recent-actions/{log_id}/undo",
    response_model=RecentActionUndoResponse,
    summary="Annule une des dernières actions (seulement depuis l'appareil qui l'a faite, sans appel au LLM)",
)
async def undo_recent_action(
    log_id: int,
    session_id: str = Query(..., min_length=1, description="Session de l'appareil qui demande l'annulation"),
) -> RecentActionUndoResponse:
    db = get_database_manager()
    log = db.get_conversation_log(log_id)
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Action {log_id} introuvable dans le journal.")
    batch_id = undo_batch_id(log)
    if batch_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cette action ne peut pas être annulée depuis la liste (dis « annule ça » juste après l'avoir faite).",
        )
    try:
        outcome = build_undo_service(get_sport_connector(), get_meals_connector()).undo_batch(session_id, batch_id)
    except UndoError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AgentUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    spoken = f"C'est annulé : {', '.join(outcome.restored)}."
    parameters: Dict[str, Any] = {"undone_log_id": log_id, "undone_action": outcome.model_dump()}
    db.log_conversation(
        raw_query=f"Annuler : {action_label(log) or 'action'}", intent=UNDO_RECENT_ACTION_INTENT,
        spoken_response=spoken, session_id=session_id, parameters=parameters,
    )
    return RecentActionUndoResponse(
        spoken_response=spoken, restored=outcome.restored, sport_session_ids=outcome.sport_session_ids,
    )
