"""Router FastAPI de l'écran « Budget » de la PWA (Phase 10) : suivi (7a) et formulaire Dépense / Revenu (7b).

Passe par `BudgetConnector`, comme l'agent vocal : même cache (3 min, invalidé par chaque saisie), mêmes erreurs
explicites sur la structure du classeur. Une saisie du formulaire réutilise les écritures vocales (`BudgetTools`) et
est inscrite au journal des conversations : elle apparaît dans « Dernières actions », annulable depuis cet appareil.
"""
from datetime import date as dt_date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator

from app.connectors.sheets.budget_connector import BudgetConnectorError, gspread
from app.connectors.sheets.budget_models import BudgetOverview
from app.core.agent.tools.budget_models import AddExpenseArgs, AddIncomeArgs, BudgetEntryView
from app.core.agent.tools.budget_tools import BudgetToolError, BudgetTools
from app.core.agent.undo import UndoJournal
from app.core.database import get_database_manager
from app.core.dependencies import get_budget_connector, get_budget_connector_error
from app.core.home.recent_actions import BUDGET_FORM_INTENT, budget_form_label
from app.core.security import verify_api_key

router = APIRouter(
    prefix="/api/v1/budget",
    tags=["Budget"],
    dependencies=[Depends(verify_api_key)],
)

_SHEETS_ERRORS: tuple = (BudgetConnectorError,) + ((gspread.exceptions.APIError,) if gspread is not None else ())


class BudgetFormEntry(BaseModel):
    """Formulaire Dépense / Revenu ; `categorie` = nom exact choisi dans la liste de l'écran."""
    type: Literal["depense", "revenu"]
    montant: float = Field(gt=0)
    categorie: str = Field(min_length=1)
    libelle: str = Field(description="Écrit « Otis : <libellé> » dans le classeur.")
    date: Optional[dt_date] = Field(None, description="Vide = aujourd'hui.")
    swile: bool = False
    remboursement: bool = False
    session_id: str = Field(min_length=1, description="Session de l'appareil : lui seul peut annuler la saisie.")

    @field_validator("libelle")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Le libellé est vide.")
        return value.strip()

    @model_validator(mode="after")
    def _income_options(self) -> "BudgetFormEntry":
        if self.type == "revenu" and (self.swile or self.remboursement):
            raise ValueError("Un revenu ne peut être ni payé en Swile ni un remboursement.")
        return self


class BudgetFormResult(BaseModel):
    message: str
    action_id: int = Field(description="Entrée du journal : à annuler via /api/v1/home/recent-actions/{id}/undo.")
    ligne: BudgetEntryView


def _connector_or_503():
    connector = get_budget_connector()
    if connector is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Classeur Budget indisponible : {get_budget_connector_error() or 'non configuré'}.",
        )
    return connector


@router.get("/overview", response_model=BudgetOverview)
def get_overview() -> BudgetOverview:
    """503 si le classeur est indisponible (cause exacte), 502 si sa structure a changé ou si Google refuse la lecture."""
    connector = _connector_or_503()
    try:
        return connector.get_overview()
    except _SHEETS_ERRORS as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/entries", response_model=BudgetFormResult, status_code=status.HTTP_201_CREATED)
def add_entry(form: BudgetFormEntry) -> BudgetFormResult:
    """422 si la catégorie n'est pas permise (rien n'est écrit), 503 classeur indisponible, 502 structure / Google."""
    tools = BudgetTools(_connector_or_503())  # sans noms appris : la catégorie vient d'une liste, rien à apprendre
    try:
        if form.type == "revenu":
            mutation = tools.add_income(AddIncomeArgs(
                montant=form.montant, type=form.categorie, libelle=form.libelle, date=form.date))
        else:
            mutation = tools.add_expense(AddExpenseArgs(
                montant=form.montant, categorie=form.categorie, libelle=form.libelle, date=form.date,
                swile=form.swile, remboursement=form.remboursement,
            ))
    except BudgetToolError as exc:
        if isinstance(exc.__cause__, BudgetConnectorError):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except _SHEETS_ERRORS as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    db = get_database_manager()
    fields = form.model_dump(mode="json", exclude={"session_id"})
    message = budget_form_label(fields)
    batch_id = UndoJournal(db).record(form.session_id, mutation.undos)
    action_id = db.log_conversation(
        raw_query=f"Formulaire Budget : {form.libelle}", intent=BUDGET_FORM_INTENT, spoken_response=message,
        session_id=form.session_id,
        parameters={"form": fields, "ligne": mutation.ligne.model_dump(mode="json"), "undo_batch_id": batch_id},
    )
    return BudgetFormResult(message=message, action_id=action_id, ligne=mutation.ligne)
