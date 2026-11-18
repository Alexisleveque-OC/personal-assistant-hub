"""Import d'une séance par capture d'écran (Strava, Decathlon Coach, montre CW500 M…) via Gemini Vision.

Routeur HTTP : lecture du fichier, analyse vision, garde-fou de date ; la logique métier est dans
app/core/sport_screenshot_import.py.
"""
from datetime import date
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from app.core.date_resolver import format_natural_spoken_date
from app.core.screenshot_date import parse_screenshot_date
from app.core.security import verify_api_key
from app.core.sport_screenshot_import import ScreenshotImportError, import_screenshot_session
from app.core.vision.sport_vision_service import VisionServiceUnavailableError, get_sport_vision_service
from app.connectors.sheets.sport_models import SportSessionStatus
from app.routers.sport import get_sport_connector_dep

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/sport",
    tags=["Sport"],
    dependencies=[Depends(verify_api_key)],
)

# Code d'erreur stable permettant au frontend de proposer la saisie manuelle de la date
DATE_MISSING_ERROR_HEADERS = {"X-Error-Code": "screenshot_date_missing"}


@router.post(
    "/import-screenshot",
    summary="Importe et extrait les métriques d'une séance depuis une capture d'écran via Gemini Vision",
)
async def import_sport_screenshot(
    file: UploadFile = File(...),
    reference_date: Optional[date] = Query(None, description="Date de référence pour la résolution relative (ex: Hier)"),
    connector=Depends(get_sport_connector_dep),
):
    """Analyse une capture d'écran (Strava, Decathlon Coach, montre CW500 M...) et enregistre la séance."""
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fichier image vide.",
        )

    mime_type = file.content_type or "image/jpeg"
    service = get_sport_vision_service()
    ref_d = reference_date or date.today()

    try:
        vision_data = await service.analyze_screenshot(
            image_bytes=image_bytes,
            mime_type=mime_type,
            reference_date=ref_d,
        )
    except VisionServiceUnavailableError as exc:
        logger.error(f"Gemini Vision indisponible pour l'import de capture sportive : {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error(f"Erreur d'analyse vision de capture sportive : {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Échec de l'analyse d'image par Gemini Vision : {exc}",
        )

    if not vision_data or not vision_data.get("is_sport_session"):
        msg = vision_data.get("message") if vision_data else None
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg or "Cette image ne semble pas être une capture d'écran de séance sportive.",
        )

    # Résolution résiliente de la date (formats ISO, DD/MM/YYYY, '08 oct. 2026', relatif...)
    raw_date = vision_data.get("date")
    has_explicit_date = bool(raw_date and str(raw_date).strip().lower() not in ("none", "null", ""))

    # Garde-fou 1 : Si aucune date n'a été détectée dans l'image et qu'aucune date de référence n'a été fournie,
    # ne JAMAIS retomber sur la date du jour : l'utilisateur doit préciser la date (paramètre reference_date).
    if not has_explicit_date and reference_date is None:
        today_session = connector.get_session(ref_d)
        if today_session and today_session.statut == SportSessionStatus.REALISE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Impossible d'extraire la date de la séance depuis la capture d'écran. "
                    f"Une séance réalisée existe déjà pour aujourd'hui ({today_session.distance_km} km). "
                    f"L'import automatique est bloqué pour protéger vos données. Veuillez préciser la date manuellement."
                ),
                headers=DATE_MISSING_ERROR_HEADERS,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Impossible d'extraire la date de la séance depuis la capture d'écran ({vision_data.get('app_source', 'source inconnue')}). "
                f"Aucune séance n'a été enregistrée. Veuillez préciser la date manuellement."
            ),
            headers=DATE_MISSING_ERROR_HEADERS,
        )

    target_date = parse_screenshot_date(raw_date, reference_date=ref_d)
    vision_data["date"] = target_date.isoformat()
    spoken_date = format_natural_spoken_date(target_date, reference_date=date.today())

    try:
        return import_screenshot_session(connector, vision_data, target_date, spoken_date)
    except ScreenshotImportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
