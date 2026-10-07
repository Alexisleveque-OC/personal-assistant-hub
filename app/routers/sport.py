"""Router FastAPI pour les fonctionnalités et le Dashboard Sport Running (Étape 7.1)."""
from datetime import date, datetime
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks

from app.config import settings
from app.core.security import verify_api_key
from app.connectors.sheets.sport_models import (
    DashboardScale,
    SportCoachTip,
    SportGamificationSummary,
    SportPeriodDashboard,
    SportSession,
    SportSessionsListResponse,
    SportSessionStatus,
    SportSessionType,
    SportSessionUpdate,
    SportSummariesListResponse,
    SportTodayResponse,
    SportWeeklySummaryWithSessions,
)
from app.core.sport_dashboard_service import (
    CoachTipProvider,
    aggregate_period,
    compare_with_previous,
)
from app.core.sport_gamification_service import SportGamificationService

from app.core.dependencies import get_sport_connector, get_sport_connector_error

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
    """Dépendance FastAPI pour obtenir le SportConnector actif."""
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


@router.get("/sessions", response_model=SportSessionsListResponse)
async def get_sport_sessions(
    order: str = Query("desc", description="Ordre de tri par date : 'desc' (antichronologique) ou 'asc'"),
    statut: Optional[str] = Query(None, description="Filtrer par statut (ex: Réalisé, Prévu)"),
    type_seance: Optional[str] = Query(None, description="Filtrer par type de séance (ex: EF, Fractionné, Renforcement)"),
    limit: int = Query(100, ge=1, le=500, description="Limite pour la pagination"),
    offset: int = Query(0, ge=0, description="Offset pour la pagination"),
    connector=Depends(get_sport_connector_dep),
):
    """Retourne la liste des séances avec tri chronologique / antichronologique et filtres."""
    all_sessions = connector.get_all_sessions()

    filtered = []
    for s in all_sessions:
        if statut:
            target_st = statut.strip().lower()
            current_st = s.statut.value.lower() if hasattr(s.statut, "value") else str(s.statut).lower()
            if target_st != current_st:
                continue

        if type_seance:
            target_tp = type_seance.strip().lower()
            current_tp = s.type_seance.value.lower() if hasattr(s.type_seance, "value") else str(s.type_seance).lower()
            if target_tp != current_tp:
                continue

        filtered.append(s)

    # Tri par date
    is_desc = order.strip().lower() != "asc"
    filtered.sort(key=lambda s: s.date, reverse=is_desc)

    total = len(filtered)
    paginated = filtered[offset : offset + limit]

    return SportSessionsListResponse(
        sessions=paginated,
        total=total,
    )


@router.get("/summaries", response_model=SportSummariesListResponse)
async def get_sport_summaries(
    annee: Optional[int] = Query(None, description="Filtrer par année"),
    include_sessions: bool = Query(True, description="Inclure les séances détaillées rattachées à la semaine"),
    order: str = Query("desc", description="Ordre de tri : 'desc' ou 'asc'"),
    limit: int = Query(52, ge=1, le=200, description="Limite de pagination"),
    offset: int = Query(0, ge=0, description="Offset de pagination"),
    connector=Depends(get_sport_connector_dep),
):
    """Retourne l'historique des synthèses hebdomadaires avec option d'imbrication des séances."""
    raw_summaries = connector.get_all_summaries(year=annee)

    is_desc = order.strip().lower() != "asc"
    raw_summaries.sort(key=lambda item: (item.annee, item.semaine), reverse=is_desc)

    total = len(raw_summaries)
    paginated = raw_summaries[offset : offset + limit]

    results: List[SportWeeklySummaryWithSessions] = []
    for summary in paginated:
        seances = []
        if include_sessions:
            seances = connector.get_week_sessions(summary.semaine, summary.annee)
            seances.sort(key=lambda s: s.date)
        results.append(SportWeeklySummaryWithSessions(summary=summary, seances=seances))

    return SportSummariesListResponse(
        summaries=results,
        total=total,
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


@router.post(
    "/sync-activity",
    summary="Synchronise une activité Strava vers Google Sheets",
)
async def sync_strava_activity(
    activity: dict,
    background_tasks: BackgroundTasks = None,
    connector=Depends(get_sport_connector_dep),
):
    """Synchronise une activité Strava (depuis webhook ou polling) vers Google Sheets."""
    strava_id = str(activity.get("id", ""))
    name = activity.get("name", "Sortie course")
    act_type = activity.get("type", "Run")
    dist_m = float(activity.get("distance", 0.0))
    dist_km = round(dist_m / 1000.0, 2)
    moving_time = int(activity.get("moving_time", 0))
    d_plus = int(activity.get("total_elevation_gain", 0))

    start_date_str = activity.get("start_date", "")
    if start_date_str:
        try:
            dt = datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))
            act_date = dt.date()
        except Exception:
            act_date = date.today()
    else:
        act_date = date.today()

    session = SportSession(
        date=act_date,
        semaine=act_date.isocalendar()[1],
        statut=SportSessionStatus.REALISE,
        type_seance=SportSessionType.EF,
        distance_km=dist_km,
        duree_secondes=moving_time,
        denivele_d_plus=d_plus,
        notes=f"Sync Strava : {name}",
        strava_id=strava_id,
    )

    if connector:
        saved = connector.log_session(session)
        if saved:
            session = saved

    return {
        "success": True,
        "message": f"Activité Strava {strava_id} synchronisée",
        "distance_km": dist_km,
        "session": session.model_dump(),
    }
