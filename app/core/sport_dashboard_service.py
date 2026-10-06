"""Service pur de calcul et d'agrégation pour le Dashboard Sport Running et le Coach Otis (Étape 7.1)."""
import calendar
from datetime import date, datetime, timedelta
import hashlib
import json
import logging
import re
from typing import Any, Callable, Coroutine, Dict, List, Optional

from app.connectors.sheets.sport_models import (
    CoachTipLevel,
    DashboardScale,
    MetricTrend,
    PeriodSeriesPoint,
    PeriodTotals,
    SessionMetricDelta,
    SportCoachTip,
    SportPeriodDashboard,
    SportSession,
    SportSessionComparison,
    SportSessionStatus,
    SportSessionType,
    calculate_pace_min_km,
    calculate_speed_kmh,
    format_pace,
)

logger = logging.getLogger(__name__)


def compare_with_previous(
    current: SportSession,
    history: List[SportSession],
) -> Optional[SportSessionComparison]:
    """Compare une séance (réalisée ou planifiée) à la dernière séance réalisée du même type."""
    # Recherche dans l'historique antérieur par date
    candidates = [
        s for s in history
        if s.statut == SportSessionStatus.REALISE
        and s.type_seance == current.type_seance
        and s.date < current.date
    ]
    if not candidates:
        return None

    # Tri par date décroissante pour prendre la plus récente
    candidates.sort(key=lambda s: s.date, reverse=True)
    previous = candidates[0]

    # Si la séance actuelle n'est pas encore réalisée, on renvoie la séance précédente en référence sans deltas
    if current.statut != SportSessionStatus.REALISE:
        return SportSessionComparison(
            current_session=current,
            previous_session=previous,
            deltas=[],
        )

    deltas: List[SessionMetricDelta] = []

    # 1. Vitesse km/h
    cur_vit = current.vitesse_kmh
    prev_vit = previous.vitesse_kmh
    if cur_vit is not None and prev_vit is not None and prev_vit > 0:
        diff_pct = round(((cur_vit - prev_vit) / prev_vit) * 100.0, 1)
        trend = MetricTrend.UP if diff_pct > 2.0 else (MetricTrend.DOWN if diff_pct < -2.0 else MetricTrend.STABLE)
        deltas.append(SessionMetricDelta(
            metric="vitesse_kmh",
            current=cur_vit,
            previous=prev_vit,
            delta_pct=diff_pct,
            trend=trend,
        ))

    # 2. Distance km
    cur_dist = current.distance_km
    prev_dist = previous.distance_km
    if cur_dist is not None and prev_dist is not None and prev_dist > 0:
        diff_pct = round(((cur_dist - prev_dist) / prev_dist) * 100.0, 1)
        trend = MetricTrend.UP if diff_pct > 2.0 else (MetricTrend.DOWN if diff_pct < -2.0 else MetricTrend.STABLE)
        deltas.append(SessionMetricDelta(
            metric="distance_km",
            current=cur_dist,
            previous=prev_dist,
            delta_pct=diff_pct,
            trend=trend,
        ))

    # 3. Km-Effort
    cur_kme = current.km_effort
    prev_kme = previous.km_effort
    if cur_kme is not None and prev_kme is not None and prev_kme > 0:
        diff_pct = round(((cur_kme - prev_kme) / prev_kme) * 100.0, 1)
        trend = MetricTrend.UP if diff_pct > 2.0 else (MetricTrend.DOWN if diff_pct < -2.0 else MetricTrend.STABLE)
        deltas.append(SessionMetricDelta(
            metric="km_effort",
            current=cur_kme,
            previous=prev_kme,
            delta_pct=diff_pct,
            trend=trend,
        ))

    return SportSessionComparison(
        current_session=current,
        previous_session=previous,
        deltas=deltas,
    )


def _compute_period_totals(sessions_in_period: List[SportSession]) -> PeriodTotals:
    """Calcule les totaux d'une liste de séances sur une période."""
    realised = [s for s in sessions_in_period if s.statut == SportSessionStatus.REALISE]
    planned = [s for s in sessions_in_period if s.statut == SportSessionStatus.PLANIFIE]

    nb_seances = len(realised)
    nb_renfo = sum(1 for s in realised if s.type_seance == SportSessionType.RENFORCEMENT)
    nb_prevues = len(planned)

    dist_tot = sum(s.distance_km or 0.0 for s in realised)
    kme_tot = sum(s.km_effort or 0.0 for s in realised)
    dur_tot = sum(s.duree_secondes or 0 for s in realised)
    charge_rpe_tot = sum(s.charge_rpe or 0 for s in realised)

    # Durée et km des courses uniquement (pour exclure le renfo du calcul de vitesse / allure)
    running = [s for s in realised if s.type_seance != SportSessionType.RENFORCEMENT and (s.distance_km or 0) > 0]
    run_dist = sum(s.distance_km or 0.0 for s in running)
    run_dur = sum(s.duree_secondes or 0 for s in running)

    vit_moy = calculate_speed_kmh(run_dist, run_dur) if (run_dist > 0 and run_dur > 0) else None
    allure_fmt = None
    if run_dist > 0 and run_dur > 0:
        pace_sec = calculate_pace_min_km(run_dist, run_dur)
        allure_fmt = format_pace(pace_sec)

    return PeriodTotals(
        nb_seances=nb_seances,
        nb_renfo=nb_renfo,
        nb_prevues=nb_prevues,
        distance_km=round(dist_tot, 2),
        km_effort=round(kme_tot, 2),
        duree_secondes=dur_tot,
        charge_rpe=charge_rpe_tot,
        vitesse_kmh=vit_moy,
        allure_formatted=allure_fmt,
    )


def aggregate_period(
    history: List[SportSession],
    scale: DashboardScale,
    ref_date: Optional[date] = None,
) -> SportPeriodDashboard:
    """Agrège l'historique sur l'échelle demandée (Semaine, Mois, Année)."""
    target_date = ref_date or date.today()

    if scale == DashboardScale.WEEK:
        iso_year, iso_week, _ = target_date.isocalendar()
        monday = date.fromisocalendar(iso_year, iso_week, 1)
        sunday = monday + timedelta(days=6)

        week_sessions = [s for s in history if s.date >= monday and s.date <= sunday]
        totals = _compute_period_totals(week_sessions)

        # Série temporelle des 8 dernières semaines glissantes
        series: List[PeriodSeriesPoint] = []
        weeks_active_kme: List[float] = []

        for offset in range(7, -1, -1):
            w_start = monday - timedelta(weeks=offset)
            w_end = w_start + timedelta(days=6)
            w_iso_year, w_iso_num, _ = w_start.isocalendar()
            s_in_w = [s for s in history if s.date >= w_start and s.date <= w_end]
            w_tot = _compute_period_totals(s_in_w)

            is_cur = (offset == 0)
            series.append(PeriodSeriesPoint(
                label=f"S{w_iso_num}",
                km_effort=w_tot.km_effort,
                distance_km=w_tot.distance_km,
                duree_secondes=w_tot.duree_secondes,
                vitesse_kmh=w_tot.vitesse_kmh,
                charge_rpe=w_tot.charge_rpe,
                is_current=is_cur,
            ))
            if not is_cur and w_tot.km_effort > 0:
                weeks_active_kme.append(w_tot.km_effort)

        # Semaine précédente (S-1) pour le plafond +10%
        prev_w_kme = series[-2].km_effort if len(series) >= 2 else 0.0
        plafond = round(prev_w_kme * 1.10, 1) if prev_w_kme > 0 else None

        # Alerte sécurité
        alerte = None
        if prev_w_kme > 0 and totals.km_effort > 0:
            evol = round(((totals.km_effort - prev_w_kme) / prev_w_kme) * 100.0, 1)
            if evol > 15.0:
                alerte = f"🔴 Risque Blessure (+{evol}%)"
            elif evol > 10.0:
                alerte = f"🟡 Vigilance (+{evol}%)"
            else:
                alerte = f"🟢 Progression Saine ({evol:+}%)"
        elif totals.km_effort > 0:
            alerte = "🟢 Première semaine enregistrée"

        # Moyenne de référence des semaines passées actives
        moy_ref = round(sum(weeks_active_kme) / len(weeks_active_kme), 1) if weeks_active_kme else None
        ecart_moy = None
        if moy_ref and moy_ref > 0:
            ecart_moy = round(((totals.km_effort - moy_ref) / moy_ref) * 100.0, 1)

        return SportPeriodDashboard(
            scale=DashboardScale.WEEK,
            label=f"Semaine {iso_week} · {iso_year}",
            start_date=monday,
            end_date=sunday,
            totals=totals,
            series=series,
            plafond_km_effort=plafond,
            alerte_securite=alerte,
            moyenne_km_effort_reference=moy_ref,
            ecart_moyenne_pct=ecart_moy,
        )

    elif scale == DashboardScale.MONTH:
        cur_year = target_date.year
        cur_month = target_date.month
        _, num_days = calendar.monthrange(cur_year, cur_month)
        start_month = date(cur_year, cur_month, 1)
        end_month = date(cur_year, cur_month, num_days)

        month_sessions = [s for s in history if s.date >= start_month and s.date <= end_month]
        totals = _compute_period_totals(month_sessions)

        month_names_fr = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
        label = f"{month_names_fr[cur_month - 1]} {cur_year}"

        # Découpage du mois en semaines ISO couvertes
        series: List[PeriodSeriesPoint] = []
        cur_w_start = start_month - timedelta(days=start_month.weekday())
        while cur_w_start <= end_month:
            cur_w_end = cur_w_start + timedelta(days=6)
            # Intersection avec le mois
            eff_start = max(cur_w_start, start_month)
            eff_end = min(cur_w_end, end_month)
            s_in_w = [s for s in history if s.date >= eff_start and s.date <= eff_end]
            w_tot = _compute_period_totals(s_in_w)
            iso_w_num = cur_w_start.isocalendar()[1]
            is_cur = (target_date >= cur_w_start and target_date <= cur_w_end)

            series.append(PeriodSeriesPoint(
                label=f"S{iso_w_num}",
                km_effort=w_tot.km_effort,
                distance_km=w_tot.distance_km,
                duree_secondes=w_tot.duree_secondes,
                vitesse_kmh=w_tot.vitesse_kmh,
                charge_rpe=w_tot.charge_rpe,
                is_current=is_cur,
            ))
            cur_w_start += timedelta(days=7)

        # Moyenne du mois précédent si présent
        prev_month_date = start_month - timedelta(days=1)
        prev_m_start = date(prev_month_date.year, prev_month_date.month, 1)
        prev_m_end = prev_month_date
        prev_m_sessions = [s for s in history if s.date >= prev_m_start and s.date <= prev_m_end]
        prev_m_tot = _compute_period_totals(prev_m_sessions)
        moy_ref = prev_m_tot.km_effort if prev_m_tot.km_effort > 0 else None
        ecart_moy = None
        if moy_ref and moy_ref > 0:
            ecart_moy = round(((totals.km_effort - moy_ref) / moy_ref) * 100.0, 1)

        return SportPeriodDashboard(
            scale=DashboardScale.MONTH,
            label=label,
            start_date=start_month,
            end_date=end_month,
            totals=totals,
            series=series,
            plafond_km_effort=None,
            alerte_securite=None,
            moyenne_km_effort_reference=moy_ref,
            ecart_moyenne_pct=ecart_moy,
        )

    elif scale == DashboardScale.YEAR:
        cur_year = target_date.year
        start_year = date(cur_year, 1, 1)
        end_year = date(cur_year, 12, 31)

        year_sessions = [s for s in history if s.date.year == cur_year]
        totals = _compute_period_totals(year_sessions)

        months_short = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
        series: List[PeriodSeriesPoint] = []
        for m_idx in range(1, 13):
            _, last_d = calendar.monthrange(cur_year, m_idx)
            m_s = date(cur_year, m_idx, 1)
            m_e = date(cur_year, m_idx, last_d)
            s_in_m = [s for s in history if s.date >= m_s and s.date <= m_e]
            m_tot = _compute_period_totals(s_in_m)
            series.append(PeriodSeriesPoint(
                label=months_short[m_idx - 1],
                km_effort=m_tot.km_effort,
                distance_km=m_tot.distance_km,
                duree_secondes=m_tot.duree_secondes,
                vitesse_kmh=m_tot.vitesse_kmh,
                charge_rpe=m_tot.charge_rpe,
                is_current=(m_idx == target_date.month),
            ))

        return SportPeriodDashboard(
            scale=DashboardScale.YEAR,
            label=f"Saison {cur_year}",
            start_date=start_year,
            end_date=end_year,
            totals=totals,
            series=series,
            plafond_km_effort=None,
            alerte_securite=None,
            moyenne_km_effort_reference=None,
            ecart_moyenne_pct=None,
        )

    raise ValueError(f"Échelle non supportée : {scale}")


# --- Règles de secours (fallback sans LLM) ---

PAIN_REGEX = re.compile(r"\b(douleur|p[ée]riostite|tibia|mal|g[êe]ne|blessure)\b", re.IGNORECASE)


def build_fallback_coach_tip(
    history: List[SportSession],
    ref_date: date,
    fallback_reason: Optional[str] = None,
) -> SportCoachTip:
    """Génère un conseil coach déterministe en ultime recours (règles sportives saines)."""
    # 1. Vérification des douleurs récentes (J-7)
    recent_limit = ref_date - timedelta(days=7)
    recent_sessions = [s for s in history if s.date >= recent_limit and s.date <= ref_date]

    pain_notes = []
    for s in recent_sessions:
        for txt in [s.remarques, s.notes]:
            if txt and PAIN_REGEX.search(txt):
                pain_notes.append(txt)

    if pain_notes:
        return SportCoachTip(
            message=(
                "⚠️ Alerte Périostite / Douleur : Une gêne a été signalée récemment. "
                "Privilégie les surfaces souples (herbe, terre), proscris le bitume et prends un jour de repos si la douleur est vive."
            ),
            niveau=CoachTipLevel.ALERTE,
            source="regles",
            fallback_reason=fallback_reason,
        )

    # 2. Vérification des RPE élevés récents (>= 8)
    high_rpes = [s for s in recent_sessions if s.statut == SportSessionStatus.REALISE and s.ressenti_rpe and s.ressenti_rpe >= 8]
    if high_rpes:
        latest_rpe = high_rpes[-1].ressenti_rpe
        return SportCoachTip(
            message=(
                f"Séance intense récente (RPE {latest_rpe}/10). Veille à une bonne hydratation, "
                "du sommeil de qualité et garde la prochaine séance en endurance fondamentale très souple."
            ),
            niveau=CoachTipLevel.VIGILANCE,
            source="regles",
            fallback_reason=fallback_reason,
        )

    # 3. Séance prévue aujourd'hui
    today_sessions = [s for s in history if s.date == ref_date]
    planned_today = [s for s in today_sessions if s.statut == SportSessionStatus.PLANIFIE]
    if planned_today:
        p = planned_today[0]
        pace_info = f" Allure conseillée : {p.allure_cible}." if p.allure_cible else ""
        prog_info = f" {p.programme}" if p.programme else ""
        return SportCoachTip(
            message=f"Séance prévue aujourd'hui : {p.type_seance.value}.{pace_info}{prog_info}".strip(),
            niveau=CoachTipLevel.INFO,
            source="regles",
            fallback_reason=fallback_reason,
        )

    # 4. Jour de repos
    return SportCoachTip(
        message="Aujourd'hui est une journée de récupération. Profite-en pour bien t'hydrater et faire tes étirements doux.",
        niveau=CoachTipLevel.INFO,
        source="regles",
        fallback_reason=fallback_reason,
    )


# --- Contexte structuré & Cache pour l'appel LLM Otis ---

def build_coach_context(
    history: List[SportSession],
    ref_date: date,
) -> Dict[str, Any]:
    """Construit un contexte déterministe (4 dernières semaines + aujourd'hui) pour nourrir le prompt LLM."""
    start_window = ref_date - timedelta(days=28)
    window_sessions = [s for s in history if s.date >= start_window and s.date <= ref_date]
    window_sessions.sort(key=lambda s: s.date)

    today_sessions = [s for s in window_sessions if s.date == ref_date]

    # Synthèse de la semaine en cours
    week_dash = aggregate_period(history, DashboardScale.WEEK, ref_date)

    recent_summary = []
    for s in window_sessions[-10:]:
        recent_summary.append({
            "date": s.date.isoformat(),
            "type": s.type_seance.value,
            "statut": s.statut.value,
            "distance_km": s.distance_km,
            "duree_minutes": (s.duree_secondes // 60) if s.duree_secondes else None,
            "allure": s.allure_formatted or s.allure_cible,
            "rpe": s.ressenti_rpe,
            "remarques": s.remarques,
            "programme": s.programme,
        })

    today_summary = [
        {
            "type": s.type_seance.value,
            "statut": s.statut.value,
            "programme": s.programme,
            "allure_cible": s.allure_cible,
            "rpe": s.ressenti_rpe,
            "remarques": s.remarques,
        }
        for s in today_sessions
    ]

    return {
        "date_du_jour": ref_date.isoformat(),
        "semaine_en_cours": {
            "label": week_dash.label,
            "km_effort_actuel": week_dash.totals.km_effort,
            "plafond_km_effort": week_dash.plafond_km_effort,
            "alerte_securite": week_dash.alerte_securite,
        },
        "seances_du_jour": today_summary,
        "seances_recentes": recent_summary,
    }


def _hash_context(context: Dict[str, Any]) -> str:
    """Génère un hash SHA-256 stable du contexte pour servir de clé de cache."""
    canonical_json = json.dumps(context, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class CoachTipProvider:
    """Gère le cache en mémoire des conseils d'Otis et le fallback fail-safe."""

    def __init__(self) -> None:
        self._cache: Dict[str, SportCoachTip] = {}
        self._cached_dates: Dict[str, date] = {}

    def _purge_old_dates(self, current_date: date) -> None:
        """Purge les entrées des jours antérieurs."""
        to_del = [k for k, d in self._cached_dates.items() if d < current_date]
        for k in to_del:
            self._cache.pop(k, None)
            self._cached_dates.pop(k, None)

    async def get_tip(
        self,
        history: List[SportSession],
        ref_date: date,
        llm_caller: Optional[Callable[[Dict[str, Any]], Coroutine[Any, Any, SportCoachTip]]] = None,
    ) -> SportCoachTip:
        """Récupère le conseil Otis (mis en cache), appelle le LLM si nécessaire, ou bascule sur les règles."""
        self._purge_old_dates(ref_date)
        context = build_coach_context(history, ref_date)
        cache_key = f"{ref_date.isoformat()}:{_hash_context(context)}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        if llm_caller:
            try:
                tip = await llm_caller(context)
                if tip and tip.source == "otis":
                    self._cache[cache_key] = tip
                    self._cached_dates[cache_key] = ref_date
                    return tip
            except Exception as exc:
                logger.warning(f"Échec de l'appel LLM pour le conseil Otis : {exc}")
                return build_fallback_coach_tip(history, ref_date, fallback_reason=str(exc))

        # Sans appel LLM configuré
        return build_fallback_coach_tip(history, ref_date, fallback_reason="no_llm_caller")
