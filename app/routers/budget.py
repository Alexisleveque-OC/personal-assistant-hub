"""Router FastAPI de l'écran « Budget » de la PWA (Phase 10, étape 7a) : suivi en lecture seule du classeur Budget.

Passe par `BudgetConnector`, comme l'agent vocal : même cache (3 min, invalidé par chaque saisie d'Otis), mêmes
erreurs explicites sur la structure du classeur.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.connectors.sheets.budget_connector import BudgetConnectorError, gspread
from app.connectors.sheets.budget_models import BudgetOverview
from app.core.dependencies import get_budget_connector, get_budget_connector_error
from app.core.security import verify_api_key

router = APIRouter(
    prefix="/api/v1/budget",
    tags=["Budget"],
    dependencies=[Depends(verify_api_key)],
)

_SHEETS_ERRORS: tuple = (BudgetConnectorError,) + ((gspread.exceptions.APIError,) if gspread is not None else ())


@router.get("/overview", response_model=BudgetOverview)
def get_overview() -> BudgetOverview:
    """503 si le classeur est indisponible (cause exacte), 502 si sa structure a changé ou si Google refuse la lecture."""
    connector = get_budget_connector()
    if connector is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Classeur Budget indisponible : {get_budget_connector_error() or 'non configuré'}.",
        )
    try:
        return connector.get_overview()
    except _SHEETS_ERRORS as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
