"""Semaines à cheval sur deux années : une séance appartient à la semaine ISO ET à l'année ISO de sa date.

Le 01/01/2027 est en semaine 53 de 2026 (une « semaine 53 de 2027 » n'existe pas) ; le 29/12/2025 est en semaine 1 de 2026.
"""
from datetime import date

import pytest

from app.connectors.sheets.sport_models import SportSessionCreate, SportSessionStatus, SportSessionType
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.tools.sport_models import LogSessionArgs
from app.core.agent.tools.sport_tools import SportTools


@pytest.fixture
def connector(isolate_sqlite_database):
    return SqlSportConnector(isolate_sqlite_database)


def _log(connector, day: date, km: float):
    return connector.log_session(SportSessionCreate(
        date=day, statut=SportSessionStatus.REALISE, type_seance=SportSessionType.EF,
        distance_km=km, duree_secondes=1800,
    ))


def test_session_on_new_year_day_counts_in_week_53_of_the_previous_iso_year(connector, isolate_sqlite_database):
    _log(connector, date(2026, 12, 28), 5.0)
    _log(connector, date(2027, 1, 1), 7.0)  # échouait : « semaine 53 de 2027 » n'existe pas

    assert isolate_sqlite_database.get_sport_weekly_summary(53, 2026)["km_total"] == 12.0
    assert isolate_sqlite_database.get_sport_weekly_summary(53, 2027) is None


def test_end_of_december_session_counts_in_week_1_of_the_next_iso_year(connector, isolate_sqlite_database):
    _log(connector, date(2025, 12, 29), 4.0)
    _log(connector, date(2026, 1, 2), 6.0)

    assert sorted(s.date for s in connector.get_week_sessions(1, 2026)) == [date(2025, 12, 29), date(2026, 1, 2)]
    assert isolate_sqlite_database.get_sport_weekly_summary(1, 2026)["km_total"] == 10.0
    assert isolate_sqlite_database.get_sport_weekly_summary(1, 2025) is None


def test_moving_a_session_across_the_new_year_refreshes_both_iso_weeks(connector, isolate_sqlite_database):
    session = _log(connector, date(2026, 12, 23), 5.0)  # semaine 52 de 2026

    connector.update_session_by_id(session.id, {"date": date(2027, 1, 1)})

    assert isolate_sqlite_database.get_sport_weekly_summary(52, 2026)["km_total"] == 0
    assert isolate_sqlite_database.get_sport_weekly_summary(53, 2026)["km_total"] == 5.0


def test_summaries_rebuilt_from_sessions_use_the_iso_year(connector, isolate_sqlite_database):
    isolate_sqlite_database.add_sport_session({"date": "2025-12-30", "statut": "Réalisé", "type_seance": "EF",
                                               "distance_km": 3.0, "duree_secondes": 1200})

    summaries = connector.get_all_summaries()

    assert [(s.semaine, s.annee) for s in summaries] == [(1, 2026)]


def test_agent_logging_a_session_on_new_year_day_uses_the_iso_year(connector, isolate_sqlite_database):
    tools = SportTools(connector, today=lambda: date(2027, 1, 2))

    tools.log_sport_session(LogSessionArgs(date=date(2027, 1, 1), type_seance="EF", distance_km=8.0))

    assert isolate_sqlite_database.get_sport_weekly_summary(53, 2026)["km_total"] == 8.0
