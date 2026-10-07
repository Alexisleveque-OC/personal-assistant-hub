"""Router FastAPI pour les fonctionnalités repas et courses."""
from typing import List
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import verify_api_key
from app.core.dependencies import get_meals_connector

router = APIRouter(
    prefix="/api/v1/meals",
    tags=["Meals"],
    dependencies=[Depends(verify_api_key)],
)


class ShoppingCompletePayload(BaseModel):
    current_week_items: List[str] = Field(default_factory=list, description="Articles cochés de Cette semaine")
    waiting_items: List[str] = Field(default_factory=list, description="Articles cochés de Liste_Attente")


@router.get("/week")
async def get_week_meals():
    """Retourne le planning des repas pour la semaine complète avec ingrédients."""
    connector = get_meals_connector()
    if connector and hasattr(connector, "get_week_meal_plans"):
        week_plan = connector.get_week_meal_plans()
        return {"success": True, "week_plan": week_plan}
    return {"success": False, "week_plan": [], "message": "Connecteur non disponible"}


@router.post("/shopping/reset")
async def reset_shopping_list():
    """Réinitialise la liste de courses : décoche les articles de 'Cette semaine' et purge le cache."""
    connector = get_meals_connector()
    uncheck_count = 0
    if connector:
        if hasattr(connector, "uncheck_current_week_items"):
            uncheck_count = connector.uncheck_current_week_items()
        if hasattr(connector, "invalidate_cache"):
            connector.invalidate_cache("shopping")
    return {
        "success": True,
        "message": "Liste de courses réinitialisée avec succès.",
        "uncheck_count": uncheck_count,
    }


@router.post("/shopping/complete")
async def complete_shopping(payload: ShoppingCompletePayload):
    """Synchronise les articles achetés directement dans les feuilles 'Cette semaine' et 'Liste_Attente'."""
    connector = get_meals_connector()
    marked_cw: List[str] = []
    marked_wa: List[str] = []

    if connector:
        if payload.current_week_items and hasattr(connector, "mark_current_week_items_bought"):
            marked_cw = connector.mark_current_week_items_bought(payload.current_week_items)
        if payload.waiting_items and hasattr(connector, "mark_shopping_items_bought"):
            marked_wa = connector.mark_shopping_items_bought(payload.waiting_items)
        if hasattr(connector, "invalidate_cache"):
            connector.invalidate_cache("shopping")

    return {
        "success": True,
        "message": f"Synchronisation terminée : {len(marked_cw)} article(s) de la semaine et {len(marked_wa)} article(s) d'attente cochés dans le Google Sheet.",
        "marked_current_week": marked_cw,
        "marked_waiting": marked_wa,
    }
