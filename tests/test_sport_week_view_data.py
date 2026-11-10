"""Refonte UX (ROADMAP Étape 2, vue Semaine) : D+ total de la période, séances d'une plage de dates."""
from datetime import date

from fastapi.testclient import TestClient

from app.connectors.sheets.sport_models import DashboardScale, SportSession, SportSessionStatus, SportSessionType
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.sport_dashboard_service import aggregate_period
from app.core import dependencies
from app.main import app


def _session(day, statut=SportSessionStatus.REALISE, d_plus=0, **kw):
    return SportSession(date=day, semaine=day.isocalendar()[1], statut=statut, type_seance=SportSessionType.COURSE,
                        denivele_d_plus=d_plus, **kw)


def test_period_totals_sum_the_climb_of_completed_sessions_only():
    history = [
        _session(date(2026, 11, 9), d_plus=29, distance_km=7.01),
        _session(date(2026, 11, 11), d_plus=120, distance_km=10),
        _session(date(2026, 11, 13), statut=SportSessionStatus.PLANIFIE, d_plus=300),  # prévue : pas encore courue
        _session(date(2026, 11, 2), d_plus=500),  # semaine précédente
    ]

    dash = aggregate_period(history, DashboardScale.WEEK, date(2026, 11, 10), today=date(2026, 11, 10))

    assert dash.totals.denivele_d_plus == 149


def test_sessions_list_can_be_limited_to_a_date_range(isolate_sqlite_database, monkeypatch):
    db = isolate_sqlite_database
    # La route lit le connecteur global : il doit pointer sur la base isolée de ce test.
    monkeypatch.setattr(dependencies, "_sport_connector", SqlSportConnector(db_manager=isolate_sqlite_database))
    for day in ("2026-11-02", "2026-11-09", "2026-11-12", "2026-11-16"):
        db.add_sport_session({"date": day, "type_seance": "Course", "statut": "Réalisé"})

    res = TestClient(app).get("/api/v1/sport/sessions", params={"date_from": "2026-11-09", "date_to": "2026-11-15"})

    assert res.status_code == 200, res.text
    body = res.json()
    sessions = body.get("sessions", body.get("items"))
    assert sorted(s["date"] for s in sessions) == ["2026-11-09", "2026-11-12"]
