"""Router FastAPI pour les fonctionnalités et le Dashboard Sport Running (Étape 7.1)."""
from datetime import date
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.config import settings
from app.core.security import verify_api_key
from app.connectors.sheets.sport_models import (
    DashboardScale,
    SportCoachTip,
    SportGamificationSummary,
    SportPeriodDashboard,
    SportSession,
    SportSessionStatus,
    SportSessionType,
    SportSessionUpdate,
    SportTodayResponse,
)
from app.core.sport_dashboard_service import (
    CoachTipProvider,
    aggregate_period,
    compare_with_previous,
)
from app.core.sport_gamification_service import SportGamificationService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/sport",
    tags=["Sport"],
    dependencies=[Depends(verify_api_key)],
)

# Instance singleton du provider de conseils avec mise en cache
_coach_tip_provider = CoachTipProvider()
_gamification_service = SportGamificationService()


def get_sport_connector_dep():
    """Dépendance FastAPI pour obtenir le SportConnector actif.

    Import différé pour éviter la dépendance circulaire main -> routers.sport -> main
    comme consigné dans la dette technique de SPEC.md.
    """
    from app.main import get_sport_connector, get_sport_connector_error
    connector = get_sport_connector()
    if not connector:
        err = get_sport_connector_error() or "vérifiez la variable SPREADSHEET_SPORT_ID et l'accès Google Sheets"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Connecteur sport non disponible ({err}).",
        )
    return connector


async def _call_gemini_coach_tip(context: Dict[str, Any]) -> SportCoachTip:
    """Appelle le LLM Gemini Flash pour formuler un conseil personnalisé Otis."""
    from app.core.sport_coach_service import SportCoachService, SPORT_COACH_SYSTEM_PROMPT
    from app.core.llm.gemini_client import get_gemini_client
    import httpx, json, time

    gemini_client = get_gemini_client()
    if not gemini_client or not gemini_client.is_configured:
        raise RuntimeError("Gemini client non configuré ou hors ligne")

    prompt = (
        f"Tu es Otis, coach running d'Alexis. Voici sa forme et son historique récent :\n"
        f"{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        f"Rédige un conseil court (1 à 2 phrases max), complice et percutant pour sa journée. "
        f"Sois très attentif aux alertes de périostite, à la charge RPE et aux allures d'aisance respiratoire. "
        f"Réponds UNIQUEMENT sous forme d'un objet JSON strict avec deux champs : 'message' (str) et 'niveau' ('info' | 'vigilance' | 'alerte')."
    )

    candidates = gemini_client.get_candidate_models()
    for candidate in candidates:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{candidate}:generateContent?key={gemini_client.api_key}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": f"{SPORT_COACH_SYSTEM_PROMPT}\n\n{prompt}"}]}],
            "generationConfig": {
                "temperature": 0.3,
                "response_mime_type": "application/json",
            },
        }
        try:
            start_time = time.perf_counter()
            async with httpx.AsyncClient(timeout=gemini_client.timeout) as http_client:
                response = await http_client.post(url, json=payload)
                if response.status_code == 429:
                    gemini_client.mark_model_temporarily_unavailable(candidate, 60.0)
                    continue
                response.raise_for_status()
                data = response.json()

            gemini_client.record_request((time.perf_counter() - start_time) * 1000)
            gemini_client.set_active_working_model(candidate)

            parts = data.get("candidates", [])[0].get("content", {}).get("parts", [])
            raw_text = parts[0].get("text", "{}")
            parsed = json.loads(raw_text)
            return SportCoachTip(
                message=parsed.get("message", "Bonne séance aujourd'hui !"),
                niveau=parsed.get("niveau", "info"),
                source="otis",
            )
        except Exception as exc:
            logger.warning(f"Tentative échouée conseil Otis sur {candidate} : {exc}")
            continue

    raise RuntimeError("Tous les modèles Gemini ont échoué")


@router.get("/today", response_model=SportTodayResponse)
async def get_sport_today(
    date_param: Optional[date] = Query(None, alias="date", description="Date cible (défaut: aujourd'hui)"),
    connector=Depends(get_sport_connector_dep),
):
    """Retourne les séances du jour, les comparateurs et le conseil Otis."""
    target_date = date_param or date.today()
    all_sessions = connector.get_all_sessions()

    # Séances du jour
    today_sessions = [s for s in all_sessions if s.date == target_date]

    # Comparaisons avec les précédentes du même type
    comparisons = []
    for s in today_sessions:
        comp = compare_with_previous(s, all_sessions)
        if comp:
            comparisons.append(comp)

    # Bulle conseil Coach Otis (avec cache et fallback ultra-robuste)
    tip = await _coach_tip_provider.get_tip(
        history=all_sessions,
        ref_date=target_date,
        llm_caller=_call_gemini_coach_tip,
    )

    # Mot d'Otis / Annonce du jour (caps franchis, paliers imminents, dopamine)
    gam_summary = _gamification_service.compute_summary(all_sessions, reference_date=target_date)

    return SportTodayResponse(
        date=target_date,
        seances=today_sessions,
        comparisons=comparisons,
        coach_tip=tip,
        daily_spotlight=gam_summary.daily_spotlight,
    )


@router.patch("/session/{target_date}")
async def patch_sport_session(
    target_date: date,
    payload: Dict[str, Any],
    type_seance: Optional[str] = Query(None, description="Type de séance si plusieurs séances le même jour"),
    connector=Depends(get_sport_connector_dep),
):
    """Met à jour a posteriori une séance (RPE, remarques, alertes douleur)."""
    target_type_enum = None
    if type_seance:
        try:
            target_type_enum = SportSessionType(type_seance)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Type de séance invalide : {type_seance}",
            )

    # Récupérer target_type depuis le body JSON s'il y est
    if not target_type_enum and "target_type" in payload and payload["target_type"]:
        try:
            target_type_enum = SportSessionType(payload["target_type"])
        except ValueError:
            pass

    try:
        updated = connector.update_session(
            target_date=target_date,
            update_data=payload,
            target_type=target_type_enum,
        )
        return {
            "success": True,
            "message": f"Séance du {target_date} mise à jour.",
            "session": updated.model_dump(mode="json"),
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.get("/dashboard", response_model=SportPeriodDashboard)
async def get_sport_dashboard(
    scale: DashboardScale = Query(DashboardScale.WEEK, description="Échelle : week, month, year"),
    date_param: Optional[date] = Query(None, alias="date", description="Date de référence"),
    connector=Depends(get_sport_connector_dep),
):
    """Retourne les totaux, métriques dérivées et séries temporelles pour les graphiques."""
    target_date = date_param or date.today()
    all_sessions = connector.get_all_sessions()
    return aggregate_period(all_sessions, scale, target_date)


@router.get(
    "/gamification",
    response_model=SportGamificationSummary,
    summary="Synthèse de gamification, badges de dopamine, records et anecdotes insolites",
)
async def get_sport_gamification(
    connector=Depends(get_sport_connector_dep),
):
    """Calcule et retourne la liste des badges, paliers réguliers, PRs et anecdotes pour Otis."""
    all_sessions = connector.get_all_sessions()
    service = SportGamificationService()
    return service.compute_summary(all_sessions)
