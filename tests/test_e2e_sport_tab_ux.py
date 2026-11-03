"""E2E retours d'usage de l'onglet Sport (03/11) : ce que la PWA appelle, sur une vraie base SQLite isolée.

Séances paginées par 30 avec filtres serveur (ce que fait `fetchSportSessions`), puis dashboard d'une période passée
(la saison précédente, telle que demandée par la flèche ‹ : veille de `start_date`), en kilomètres.
"""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.dependencies import set_sport_connector
from app.main import app

client = TestClient(app)
PAGE = 30


@pytest.fixture
def db(isolate_sqlite_database):
    # 70 séances : 40 EF réalisées en 2025 (une tous les 5 jours), 30 renfo prévues ou réalisées en 2026
    start_2025 = date(2025, 1, 6)
    for i in range(40):
        isolate_sqlite_database.add_sport_session({
            "date": (start_2025 + timedelta(days=5 * i)).isoformat(), "type_seance": "EF", "statut": "Réalisé",
            "distance_km": 8.0, "duree_secondes": 3000, "denivele_d_plus": 50,
        })
    for i in range(30):
        isolate_sqlite_database.add_sport_session({
            "date": (date(2026, 1, 5) + timedelta(days=7 * i)).isoformat(), "type_seance": "Renforcement",
            "statut": "Réalisé" if i % 2 else "Prévu", "duree_secondes": 1800,
        })
    set_sport_connector(SqlSportConnector(db_manager=isolate_sqlite_database))
    yield
    set_sport_connector(None)


def _page(page: int, **filters) -> dict:
    params = {"order": "desc", "limit": PAGE, "offset": page * PAGE, **filters}
    resp = client.get("/api/v1/sport/sessions", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_sessions_come_page_by_page_newest_first(db):
    first, second, third = _page(0), _page(1), _page(2)

    assert first["total"] == 70
    assert [len(p["sessions"]) for p in (first, second, third)] == [30, 30, 10]
    dates = [s["date"] for p in (first, second, third) for s in p["sessions"]]
    assert dates == sorted(dates, reverse=True) and len(set(dates)) == 70


def test_filters_apply_to_the_whole_history_not_only_the_loaded_page(db):
    ef = _page(0, type_seance="EF")
    assert ef["total"] == 40 and len(ef["sessions"]) == 30
    assert {s["type_seance"] for s in ef["sessions"]} == {"EF"}

    planned = _page(0, statut="Prévu")
    assert planned["total"] == 15
    assert {s["statut"] for s in planned["sessions"]} == {"Prévu"}


def test_previous_season_dashboard_in_kilometres(db):
    current = client.get("/api/v1/sport/dashboard", params={"scale": "year", "date": "2026-06-15"}).json()
    assert current["label"] == "Saison 2026" and current["start_date"] == "2026-01-01"

    # Flèche ‹ : la veille du début de la période affichée
    previous_day = (date.fromisoformat(current["start_date"]) - timedelta(days=1)).isoformat()
    resp = client.get("/api/v1/sport/dashboard", params={"scale": "year", "date": previous_day})
    assert resp.status_code == 200, resp.text
    season_2025 = resp.json()

    assert season_2025["label"] == "Saison 2025"
    assert season_2025["totals"]["distance_km"] == 320.0  # 40 × 8 km
    assert season_2025["totals"]["km_effort"] == 340.0  # 40 × (8 + 50 m D+ / 100)
    assert sum(point["distance_km"] for point in season_2025["series"]) == 320.0


def test_previous_week_and_month_are_reachable_too(db):
    week = client.get("/api/v1/sport/dashboard", params={"scale": "week", "date": "2025-01-12"}).json()
    assert (week["start_date"], week["end_date"]) == ("2025-01-06", "2025-01-12")
    assert week["totals"]["distance_km"] == 16.0  # 6 et 11 janvier

    month = client.get("/api/v1/sport/dashboard", params={"scale": "month", "date": "2025-01-31"}).json()
    assert month["label"] == "Janvier 2025" and month["totals"]["nb_seances"] == 6


def test_selected_week_is_centred_with_following_weeks_and_past_season_has_no_current_month(db):
    week = client.get("/api/v1/sport/dashboard", params={"scale": "week", "date": "2025-02-05"}).json()
    labels = [p["label"] for p in week["series"]]
    assert labels == ["S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9"]
    assert [p["is_current"] for p in week["series"]].index(True) == 4  # S6, la semaine choisie
    assert week["series"][5]["distance_km"] > 0  # semaine suivante visible (EF du 10/02)

    season_2025 = client.get("/api/v1/sport/dashboard", params={"scale": "year", "date": "2025-12-31"}).json()
    assert not any(p["is_current"] for p in season_2025["series"])
