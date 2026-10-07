"""Router FastAPI pour les intégrations externes (Webhooks Strava)."""
import logging
from fastapi import APIRouter, Query, Request, BackgroundTasks

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/integrations/strava",
    tags=["Strava"],
)


@router.get("/webhook")
async def strava_webhook_challenge(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
):
    """Validation de l'abonnement webhook Strava (hub.challenge)."""
    return {"hub.challenge": hub_challenge}


@router.post("/webhook")
async def strava_webhook_event(
    request: Request,
    background_tasks: BackgroundTasks = None,
):
    """Réception des événements webhook Strava (ex: activity.created)."""
    payload = await request.json()
    logger.info(f"Webhook Strava reçu : {payload}")
    return {"status": "ok"}
