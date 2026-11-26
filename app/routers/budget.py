"""Router FastAPI de l'écran « Budget » de la PWA (Phase 10) : suivi (7a) et formulaires (7b Dépense / Revenu,
7c Échéancier et Dépense multiple).

Passe par `BudgetConnector`, comme l'agent vocal : même cache (3 min, invalidé par chaque saisie), mêmes erreurs
explicites sur la structure du classeur. Une saisie de formulaire réutilise les écritures vocales (`BudgetTools`) et
est inscrite au journal des conversations : elle apparaît dans « Dernières actions », annulable depuis cet appareil.
"""
from typing import Any, Callable, List, Tuple, TypeVar

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.connectors.sheets.budget_connector import BudgetCategoryNotFoundError, BudgetConnectorError, gspread
from app.connectors.sheets.budget_models import BudgetOverview
from app.core.agent.tools.budget_models import (
    AddExpenseArgs,
    AddIncomeArgs,
    AddInstallmentArgs,
    PredeclareSplitExpenseArgs,
    SplitPartArgs,
)
from app.core.agent.tools.budget_tools import BudgetToolError, BudgetTools
from app.core.agent.undo import UndoJournal
from app.core.database import get_database_manager
from app.core.dependencies import get_budget_connector, get_budget_connector_error
from app.core.home.recent_actions import BUDGET_FORM_INTENT, budget_form_label
from app.core.security import verify_api_key
from app.routers.budget_form_models import (
    BudgetFormAck,
    BudgetFormEntry,
    BudgetFormResult,
    InstallmentForm,
    SplitExpenseForm,
)

router = APIRouter(
    prefix="/api/v1/budget",
    tags=["Budget"],
    dependencies=[Depends(verify_api_key)],
)

_SHEETS_ERRORS: tuple = (BudgetConnectorError,) + ((gspread.exceptions.APIError,) if gspread is not None else ())
T = TypeVar("T")


def _connector_or_503():
    connector = get_budget_connector()
    if connector is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Classeur Budget indisponible : {get_budget_connector_error() or 'non configuré'}.",
        )
    return connector


def _write(action: Callable[[BudgetTools], T]) -> T:
    """Écriture vocale réutilisée, sans noms appris (la catégorie vient d'une liste : rien à apprendre).

    422 saisie refusée (catégorie, somme des parts… : rien n'est écrit), 502 structure du classeur ou refus de Google.
    """
    tools = BudgetTools(_connector_or_503())
    try:
        return action(tools)
    except BudgetToolError as exc:
        cause = exc.__cause__
        if isinstance(cause, BudgetConnectorError) and not isinstance(cause, BudgetCategoryNotFoundError):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except _SHEETS_ERRORS as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


def _journalize(form: BaseModel, raw_query: str, undos: List[Any], extra: dict) -> Tuple[str, int]:
    """Inscrit la saisie au journal avec son lot d'annulation : (libellé, identifiant de l'action)."""
    db = get_database_manager()
    fields = form.model_dump(mode="json", exclude={"session_id"})
    message = budget_form_label(fields)
    batch_id = UndoJournal(db).record(form.session_id, undos)
    action_id = db.log_conversation(
        raw_query=raw_query, intent=BUDGET_FORM_INTENT, spoken_response=message, session_id=form.session_id,
        parameters={"form": fields, **extra, "undo_batch_id": batch_id},
    )
    return message, action_id


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
    """Dépense, remboursement ou revenu (étape 7b)."""
    if form.type == "revenu":
        mutation = _write(lambda tools: tools.add_income(AddIncomeArgs(
            montant=form.montant, type=form.categorie, libelle=form.libelle, date=form.date)))
    else:
        mutation = _write(lambda tools: tools.add_expense(AddExpenseArgs(
            montant=form.montant, categorie=form.categorie, libelle=form.libelle, date=form.date,
            swile=form.swile, remboursement=form.remboursement,
        )))
    message, action_id = _journalize(
        form, f"Formulaire Budget : {form.libelle}", mutation.undos, {"ligne": mutation.ligne.model_dump(mode="json")},
    )
    return BudgetFormResult(message=message, action_id=action_id, ligne=mutation.ligne)


@router.post("/installments", response_model=BudgetFormAck, status_code=status.HTTP_201_CREATED)
def add_installment(form: InstallmentForm) -> BudgetFormAck:
    """Échéancier « Actif » à l'échéance 0 (étape 7c) ; mois de début vide = mois en cours."""
    year, month = (int(part) for part in form.mois_debut.split("-")) if form.mois_debut else (None, None)
    mutation = _write(lambda tools: tools.add_installment(AddInstallmentArgs(
        nom=form.nom, montant_total=form.montant_total, nb_echeances=form.nb_echeances, categorie=form.categorie,
        mois_debut=month, annee_debut=year, commentaire=form.commentaire,
    )))
    message, action_id = _journalize(
        form, f"Formulaire Budget : échéancier {form.nom}", mutation.undos,
        {"echeancier": mutation.echeancier.model_dump(mode="json")},
    )
    return BudgetFormAck(message=message, action_id=action_id)


@router.post("/split-expenses", response_model=BudgetFormAck, status_code=status.HTTP_201_CREATED)
def add_split_expense(form: SplitExpenseForm) -> BudgetFormAck:
    """Dépense multiple « A traiter » (étape 7c) : l'import découpera le débit correspondant entre les parts."""
    mutation = _write(lambda tools: tools.predeclare_split_expense(PredeclareSplitExpenseArgs(
        mot_cle=form.mot_cle, montant_total=form.montant_total, date=form.date,
        parts=[SplitPartArgs(categorie=part.categorie, montant=part.montant) for part in form.parts],
    )))
    message, action_id = _journalize(
        form, f"Formulaire Budget : dépense multiple {form.mot_cle}", mutation.undos,
        {"depense": mutation.depense.model_dump(mode="json")},
    )
    return BudgetFormAck(message=message, action_id=action_id)
