"""Router FastAPI pour les fonctionnalités repas et courses."""
from fastapi import APIRouter, Depends

from app.core.security import verify_api_key
from app.core.dependencies import get_meals_connector

router = APIRouter(
    prefix="/api/v1/meals",
    tags=["Meals"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("/week")
async def get_week_meals():
    """Retourne le planning des repas pour la semaine complète avec ingrédients."""
    connector = get_meals_connector()
    if connector and hasattr(connector, "get_week_meal_plans"):
        week_plan = connector.get_week_meal_plans()
        return {"success": True, "week_plan": week_plan}
    return {"success": False, "week_plan": [], "message": "Connecteur non disponible"}
