"""Tests unitaires (TDD) du service pur de dashboard running (Étape 7.1)."""
from datetime import date, timedelta
from typing import Optional

import pytest

from app.connectors.sheets.sport_models import (
    CoachTipLevel,
    DashboardScale,
    MetricTrend,
    SportCoachTip,
    SportSession,
    SportSessionStatus,
    SportSessionType,
)
from app.core.sport_dashboard_service import (
    CoachTipProvider,
    aggregate_period,
    build_coach_context,
    build_fallback_coach_tip,
    compare_with_previous,
)

REF_DATE = date(2026, 10, 7)  # Mercredi, semaine ISO 41


def _s(
    d: date,
    type_seance: SportSessionType,
    distance: Optional[float] = None,
    minutes: Optional[int] = None,
    rpe: Optional[int] = None,
    statut: SportSessionStatus = SportSessionStatus.REALISE,
    remarques: str = "",
    programme: str = "",
    allure_cible: Optional[str] = None,
) -> SportSession:
    return SportSession(
        date=d,
        semaine=d.isocalendar()[1],
        statut=statut,
        type_seance=type_seance,
        distance_km=distance,
        duree_secondes=minutes * 60 if minutes else None,
        ressenti_rpe=rpe,
        remarques=remarques,
        programme=programme,
        allure_cible=allure_cible,
    )


@pytest.fixture
def history() -> list[SportSession]:
    return [
        _s(date(2026, 9, 21), SportSessionType.FRACTIONNE, 5.0, 30, 7),  # S39
        _s(date(2026, 9, 29), SportSessionType.EF, 5.0, 30, 5),  # S40
        _s(date(2026, 10, 3), SportSessionType.SORTIE_LONGUE, 9.0, 60, 6),  # S40 (mais en octobre)
        _s(date(2026, 10, 5), SportSessionType.FRACTIONNE, 5.0, 28, 7),  # S41
        _s(date(2026, 10, 6), SportSessionType.RENFORCEMENT, None, 30, 5),  # S41
        _s(date(2026, 10, 8), SportSessionType.EF, 5.0, statut=SportSessionStatus.PLANIFIE),  # S41 prévu
    ]


# --- Comparateur de séance ---

def test_compare_with_previous_same_type_realised(history):
    current = history[3]  # Fractionné du 05/10

    comparison = compare_with_previous(current, history)

    assert comparison is not None
    assert comparison.previous_session.date == date(2026, 9, 21)
    deltas = {d.metric: d for d in comparison.deltas}
    assert deltas["vitesse_kmh"].current == 10.71
    assert deltas["vitesse_kmh"].previous == 10.0
    assert deltas["vitesse_kmh"].delta_pct == 7.1
    assert deltas["vitesse_kmh"].trend == MetricTrend.UP
    assert deltas["distance_km"].trend == MetricTrend.STABLE
    assert deltas["km_effort"].trend == MetricTrend.STABLE


def test_compare_planned_session_returns_reference_without_deltas(history):
    planned_ef = history[5]

    comparison = compare_with_previous(planned_ef, history)

    assert comparison is not None
    assert comparison.previous_session.date == date(2026, 9, 29)
    assert comparison.deltas == []


def test_compare_without_previous_same_type_returns_none(history):
    sl = history[2]
    assert compare_with_previous(sl, history) is None


# --- Agrégation multi-échelles ---

def test_aggregate_week_totals_excludes_renfo_from_pace_and_counts_planned(history):
    dash = aggregate_period(history, DashboardScale.WEEK, REF_DATE)

    assert dash.label == "Semaine 41 · 2026"
    assert dash.start_date == date(2026, 10, 5)
    assert dash.end_date == date(2026, 10, 11)
    t = dash.totals
    assert t.nb_seances == 2
    assert t.nb_renfo == 1
    assert t.nb_prevues == 1
    assert t.distance_km == 5.0
    assert t.km_effort == 5.0
    assert t.duree_secondes == 58 * 60
    assert t.charge_rpe == 28 * 7 + 30 * 5
    assert t.vitesse_kmh == 10.71  # Renfo exclu du calcul de vitesse
    assert t.allure_formatted == "05:36"


def test_aggregate_week_safety_cap_alert_and_reference_average(history):
    dash = aggregate_period(history, DashboardScale.WEEK, REF_DATE)

    assert dash.plafond_km_effort == 15.4  # S40 = 14.0 km-effort -> +10 %
    assert dash.alerte_securite is not None
    assert dash.moyenne_km_effort_reference == 9.5  # Moyenne des semaines actives précédentes (S39, S40)
    assert dash.ecart_moyenne_pct == -47.4


def test_aggregate_week_series_has_8_weeks_ending_on_current(history):
    dash = aggregate_period(history, DashboardScale.WEEK, REF_DATE)

    assert len(dash.series) == 8
    assert dash.series[-1].label == "S41"
    assert dash.series[-1].is_current is True
    s40 = next(p for p in dash.series if p.label == "S40")
    assert s40.km_effort == 14.0
    assert all(not p.is_current for p in dash.series[:-1])


def test_aggregate_month_uses_calendar_month_and_weekly_series(history):
    dash = aggregate_period(history, DashboardScale.MONTH, REF_DATE)

    assert dash.label == "Octobre 2026"
    assert dash.start_date == date(2026, 10, 1)
    assert dash.end_date == date(2026, 10, 31)
    assert dash.totals.distance_km == 14.0  # SL du 03/10 + Fractionné du 05/10
    assert [p.label for p in dash.series] == ["S40", "S41", "S42", "S43", "S44"]
    assert dash.series[0].km_effort == 9.0  # Seule la partie d'octobre de S40
    assert dash.moyenne_km_effort_reference == 10.0  # Septembre
    assert dash.plafond_km_effort is None


def test_aggregate_year_monthly_series(history):
    dash = aggregate_period(history, DashboardScale.YEAR, REF_DATE)

    assert dash.label == "Saison 2026"
    assert len(dash.series) == 12
    assert dash.series[0].label == "janv."
    assert dash.series[8].km_effort == 10.0  # Septembre
    assert dash.series[9].km_effort == 14.0
    assert dash.series[9].is_current is True
    assert dash.moyenne_km_effort_reference is None  # Aucune saison précédente


def test_aggregate_empty_history_is_safe():
    dash = aggregate_period([], DashboardScale.WEEK, REF_DATE)
    assert dash.totals.nb_seances == 0
    assert dash.totals.vitesse_kmh is None
    assert dash.plafond_km_effort is None
    assert dash.moyenne_km_effort_reference is None


# --- Conseil de secours (règles minimales) ---

def test_fallback_tip_pain_has_top_priority(history):
    sessions = history + [_s(date(2026, 10, 6), SportSessionType.EF, 4.0, 25, 5, remarques="Petite douleur au tibia")]

    tip = build_fallback_coach_tip(sessions, REF_DATE, fallback_reason="quota")

    assert tip.niveau == CoachTipLevel.ALERTE
    assert tip.source == "regles"
    assert tip.fallback_reason == "quota"


def test_fallback_tip_ignores_false_positive_words():
    """'normal' contient 'mal' mais ne doit pas déclencher d'alerte douleur."""
    sessions = [
        _s(date(2026, 10, 6), SportSessionType.EF, 5.0, 30, 4, remarques="Sensations normales"),
        _s(REF_DATE, SportSessionType.EF, 5.0, statut=SportSessionStatus.PLANIFIE,
           programme="30 min Zone 2", allure_cible="06:20/km (+/- 15s)"),
    ]

    tip = build_fallback_coach_tip(sessions, REF_DATE, fallback_reason="x")

    assert tip.niveau == CoachTipLevel.INFO
    assert "06:20/km" in tip.message


def test_fallback_tip_high_rpe_triggers_vigilance():
    sessions = [_s(date(2026, 10, 6), SportSessionType.FRACTIONNE, 5.0, 30, 8)]

    tip = build_fallback_coach_tip(sessions, REF_DATE, fallback_reason="x")

    assert tip.niveau == CoachTipLevel.VIGILANCE
    assert "8/10" in tip.message


def test_fallback_tip_rest_day_when_nothing_planned():
    tip = build_fallback_coach_tip([], REF_DATE, fallback_reason="x")
    assert tip.niveau == CoachTipLevel.INFO
    assert "récupération" in tip.message.lower()


# --- Contexte LLM & cache du conseil Otis ---

def test_build_coach_context_keeps_recent_window_only(history):
    old = _s(date(2026, 8, 1), SportSessionType.EF, 5.0, 30, 5)

    ctx = build_coach_context(history + [old], REF_DATE)

    dates = [s["date"] for s in ctx["seances_recentes"]]
    assert "2026-08-01" not in dates
    assert "2026-10-05" in dates
    assert [s["type"] for s in ctx["seances_du_jour"]] == []
    assert ctx["semaine_en_cours"]["plafond_km_effort"] == 15.4
    assert ctx == build_coach_context(history + [old], REF_DATE)  # Déterministe (empreinte de cache stable)


@pytest.mark.asyncio
async def test_coach_tip_provider_caches_until_context_changes(history):
    calls: list[dict] = []

    async def fake_llm(context: dict) -> SportCoachTip:
        calls.append(context)
        return SportCoachTip(message="Conseil Otis", niveau=CoachTipLevel.INFO, source="otis")

    provider = CoachTipProvider()
    tip1 = await provider.get_tip(history, REF_DATE, fake_llm)
    tip2 = await provider.get_tip(history, REF_DATE, fake_llm)
    assert tip1.source == "otis" and tip2.message == "Conseil Otis"
    assert len(calls) == 1

    changed = history + [_s(date(2026, 10, 7), SportSessionType.EF, 5.0, 30, 9)]
    await provider.get_tip(changed, REF_DATE, fake_llm)
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_coach_tip_provider_falls_back_on_llm_error_without_caching(history):
    attempts = {"n": 0}

    async def failing_llm(context: dict) -> SportCoachTip:
        attempts["n"] += 1
        raise RuntimeError("Quota Gemini épuisé")

    provider = CoachTipProvider()
    tip = await provider.get_tip(history, REF_DATE, failing_llm)
    await provider.get_tip(history, REF_DATE, failing_llm)

    assert tip.source == "regles"
    assert "Quota Gemini épuisé" in tip.fallback_reason
    assert attempts["n"] == 2  # Le secours n'est pas mis en cache : Otis est retenté au prochain affichage


@pytest.mark.asyncio
async def test_coach_tip_provider_purges_previous_days(history):
    async def fake_llm(context: dict) -> SportCoachTip:
        return SportCoachTip(message="ok", niveau=CoachTipLevel.INFO, source="otis")

    provider = CoachTipProvider()
    await provider.get_tip(history, REF_DATE, fake_llm)
    await provider.get_tip(history, REF_DATE + timedelta(days=1), fake_llm)

    assert len(provider._cache) == 1
