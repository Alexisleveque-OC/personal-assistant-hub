"""Tests des outils métier sport de l'agent (Phase 6.8 - Étape 1).

Principes vérifiés : modifications par identifiant uniquement, aucune fusion ni valeur inventée,
instantané avant chaque mutation et restauration exacte.
"""
from datetime import date

import pytest
from pydantic import ValidationError

from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.tools.sport_models import (
    FindSessionsArgs,
    LogSessionArgs,
    PlanSessionArgs,
    SessionChanges,
    UpdateSessionArgs,
)
from app.core.agent.tools.sport_tools import SportSessionNotFoundError, SportToolError, SportTools

TODAY = date(2026, 10, 19)  # lundi


@pytest.fixture
def db(isolate_sqlite_database):
    return isolate_sqlite_database


@pytest.fixture
def tools(db):
    return SportTools(SqlSportConnector(db_manager=db), today=lambda: TODAY)


def _seed(db, day: str, type_seance: str, statut: str = "Réalisé", **fields) -> int:
    return db.add_sport_session({"date": day, "type_seance": type_seance, "statut": statut, **fields})


# --- find_sport_sessions -----------------------------------------------------

def test_find_filters_by_type_most_recent_first(db, tools):
    old = _seed(db, "2026-09-28", "Fractionné")
    _seed(db, "2026-10-14", "EF")
    recent = _seed(db, "2026-10-12", "Fractionné")

    result = tools.find_sport_sessions(FindSessionsArgs(type_seance="Fractionné"))

    assert [s.id for s in result] == [recent, old]
    assert result[0].jour == "lundi"
    assert result[0].type_seance.value == "Fractionné"


def test_find_filters_by_date_range_status_and_limit(db, tools):
    _seed(db, "2026-10-10", "EF")
    in_range = _seed(db, "2026-10-15", "EF")
    _seed(db, "2026-10-16", "EF", statut="Prévu")
    latest = _seed(db, "2026-10-18", "Renforcement")

    result = tools.find_sport_sessions(FindSessionsArgs(
        date_from=date(2026, 10, 12), date_to=date(2026, 10, 19), statut="Réalisé", limit=2,
    ))

    assert [s.id for s in result] == [latest, in_range]


def test_find_rejects_inverted_range_and_excessive_limit():
    with pytest.raises(ValidationError, match="date_from"):
        FindSessionsArgs(date_from=date(2026, 10, 19), date_to=date(2026, 10, 1))
    with pytest.raises(ValidationError):
        FindSessionsArgs(limit=500)


# --- get_sport_session ---------------------------------------------------------

def test_get_returns_session_by_id(db, tools):
    session_id = _seed(db, "2026-10-14", "EF", distance_km=5.0, remarques="Bonnes jambes")
    view = tools.get_sport_session(session_id)
    assert (view.id, view.date, view.distance_km, view.remarques) == (session_id, date(2026, 10, 14), 5.0, "Bonnes jambes")


def test_get_unknown_id_raises_explicit_error(tools):
    with pytest.raises(SportSessionNotFoundError, match="42"):
        tools.get_sport_session(42)


# --- update_sport_session ------------------------------------------------------

def test_update_targets_only_the_given_id(db, tools):
    renfo = _seed(db, "2026-10-18", "Renforcement")
    ef = _seed(db, "2026-10-18", "EF", ressenti_rpe=4)

    result = tools.update_sport_session(UpdateSessionArgs(
        session_id=renfo, changes=SessionChanges(ressenti_rpe=3, meteo_note=2),
    ))

    assert (result.session.id, result.session.ressenti_rpe, result.session.meteo_note) == (renfo, 3, 2)
    assert db.get_sport_session_by_id(ef)["ressenti_rpe"] == 4
    assert result.undo.action == "updated"
    assert result.undo.before.ressenti_rpe is None


def test_update_can_change_type_and_date_with_week_recomputed(db, tools):
    session_id = _seed(db, "2026-10-19", "EF")
    result = tools.update_sport_session(UpdateSessionArgs(
        session_id=session_id, changes=SessionChanges(type_seance="Fractionné", date=date(2026, 10, 11)),
    ))
    row = db.get_sport_session_by_id(session_id)
    assert (row["type_seance"], row["date"], row["semaine"]) == ("Fractionné", "2026-10-11", 41)
    assert result.session.type_seance.value == "Fractionné"


def test_update_unknown_id_raises_without_side_effect(db, tools):
    existing = _seed(db, "2026-10-19", "EF")
    with pytest.raises(SportSessionNotFoundError, match="99"):
        tools.update_sport_session(UpdateSessionArgs(session_id=99, changes=SessionChanges(ressenti_rpe=5)))
    assert db.get_sport_session_by_id(existing)["ressenti_rpe"] is None


def test_changes_must_be_non_empty_and_strict():
    with pytest.raises(ValidationError, match="au moins un champ"):
        SessionChanges()
    with pytest.raises(ValidationError):
        SessionChanges(allure_moyenne="05:30")
    with pytest.raises(ValidationError):
        SessionChanges(ressenti_rpe=11)


# --- log_sport_session ---------------------------------------------------------

def test_log_always_creates_a_new_session_without_invented_values(db, tools):
    existing = _seed(db, "2026-10-19", "EF", distance_km=5.0)

    result = tools.log_sport_session(LogSessionArgs(date=TODAY, type_seance="Fractionné"))

    assert result.session.id != existing
    assert result.session.statut.value == "Réalisé"
    assert result.session.type_seance.value == "Fractionné"
    assert result.session.duree_secondes is None
    assert db.get_sport_session_by_id(existing)["type_seance"] == "EF"
    assert result.undo.action == "created" and result.undo.before is None


def test_log_in_the_future_is_rejected(tools):
    with pytest.raises(SportToolError, match="futur"):
        tools.log_sport_session(LogSessionArgs(date=date(2026, 10, 20), type_seance="EF"))


def test_log_refreshes_weekly_summary(db, tools):
    tools.log_sport_session(LogSessionArgs(date=TODAY, type_seance="EF", distance_km=6.0, duree_secondes=2100))
    summary = db.get_sport_weekly_summary(semaine=43, annee=2026)
    assert summary is not None and summary["nb_seances"] == 1


# --- plan_sport_session --------------------------------------------------------

def test_plan_creates_planned_session_without_overwriting_same_day(db, tools):
    existing = _seed(db, "2026-10-20", "Renforcement", statut="Prévu")

    result = tools.plan_sport_session(PlanSessionArgs(date=date(2026, 10, 20), type_seance="Sortie Longue", distance_km=10.0))

    assert result.session.id != existing
    assert (result.session.statut.value, result.session.type_seance.value) == ("Prévu", "Sortie Longue")
    assert db.get_sport_session_by_id(existing)["type_seance"] == "Renforcement"


def test_plan_in_the_past_is_rejected(tools):
    with pytest.raises(SportToolError, match="passé"):
        tools.plan_sport_session(PlanSessionArgs(date=date(2026, 10, 18), type_seance="EF"))


# --- undo_sport_mutation -------------------------------------------------------

def test_undo_update_restores_the_exact_row(db, tools):
    session_id = _seed(db, "2026-10-19", "EF", remarques="RAS")
    before = db.get_sport_session_by_id(session_id)

    result = tools.update_sport_session(UpdateSessionArgs(
        session_id=session_id,
        changes=SessionChanges(ressenti_rpe=7, type_seance="Fractionné", remarques="Dur", date=date(2026, 10, 12)),
    ))
    tools.undo_sport_mutation(result.undo)

    after = db.get_sport_session_by_id(session_id)
    volatile = {"updated_at", "created_at"}
    assert {k: v for k, v in after.items() if k not in volatile} == {k: v for k, v in before.items() if k not in volatile}


def test_undo_creation_deletes_the_created_session(db, tools):
    result = tools.log_sport_session(LogSessionArgs(date=TODAY, type_seance="EF"))
    tools.undo_sport_mutation(result.undo)
    assert db.get_sport_session_by_id(result.session.id) is None


def test_undo_on_missing_session_raises(db, tools):
    result = tools.log_sport_session(LogSessionArgs(date=TODAY, type_seance="EF"))
    db.delete_sport_session(result.session.id)
    with pytest.raises(SportSessionNotFoundError):
        tools.undo_sport_mutation(result.undo)


def test_default_clock_is_paris(db):
    from app.core.clock import paris_today
    assert SportTools(SqlSportConnector(db_manager=db)).today() == paris_today()
