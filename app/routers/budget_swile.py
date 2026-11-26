"""Import Swile par captures d'écran (Phase 10, étape 8) : analyse sans écriture, puis import des lignes relues.

Routeur HTTP seulement : lecture Gemini Vision (`vision.swile_vision_service`), relecture (`swile_import.review`).
"""
import logging
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from app.core.clock import paris_today
from app.core.database import get_database_manager
from app.core.security import verify_api_key
from app.core.swile_import.importer import SwileImportError, import_swile
from app.core.swile_import.models import SwileImportForm, SwileReview
from app.core.swile_import.review import SwileReviewError, build_review
from app.core.vision.gemini_vision import VisionServiceUnavailableError
from app.core.vision.swile_vision_service import get_swile_vision_service
from app.routers.budget import _SHEETS_ERRORS, _connector_or_503, _journalize
from app.routers.budget_form_models import BudgetFormAck

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/budget/swile",
    tags=["Budget"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("/analyze", response_model=SwileReview)
async def analyze_swile_captures(
    files: List[UploadFile] = File(..., description="Une ou plusieurs captures de l'appli Swile."),
    reference_date: Optional[date] = Query(None, description="Jour de l'import (dates relatives) ; vide = aujourd'hui."),
) -> SwileReview:
    """Rien n'est écrit. 400 fichier vide, 422 rien de lisible, 503 Gemini ou classeur indisponible, 502 classeur."""
    connector = _connector_or_503()
    service = get_swile_vision_service()
    captures = []
    for upload in files:
        image = await upload.read()
        if not image:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Fichier image vide : {upload.filename}.")
        try:
            captures.append(await service.analyze_screenshot(image, upload.content_type or "image/jpeg"))
        except VisionServiceUnavailableError as exc:
            logger.error(f"Gemini Vision indisponible pour l'import Swile : {exc}")
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    try:
        return build_review(captures, connector, get_database_manager(), reference_date or paris_today())
    except SwileReviewError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except _SHEETS_ERRORS as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/import", response_model=BudgetFormAck, status_code=status.HTTP_201_CREATED)
def import_swile_lines(form: SwileImportForm) -> BudgetFormAck:
    """Une seule action de « Dernières actions », annulée d'un coup. 422 catégorie refusée (rien n'est écrit),
    502 structure du classeur ou refus de Google (lignes déjà écrites retirées)."""
    connector = _connector_or_503()
    try:
        undo, learned = import_swile(connector, form, get_database_manager())
    except SwileImportError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except _SHEETS_ERRORS as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    message, action_id = _journalize(form, "Import Swile par captures", [undo, *learned], {})
    return BudgetFormAck(message=message, action_id=action_id)
