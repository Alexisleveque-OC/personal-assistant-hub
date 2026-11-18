"""Découpage du routeur sport : l'import de captures a son routeur et son service métier (sans HTTP).

Le comportement HTTP complet reste couvert par test_sport_screenshot_vision_import.py.
"""
from datetime import date

import pytest

from app.connectors.sheets.sport_models import SportSessionCreate, SportSessionStatus, SportSessionType
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.sport_screenshot_import import ScreenshotImportError, import_screenshot_session, normalize_session_type


@pytest.mark.parametrize("raw, expected", [
    ("Fractionné", SportSessionType.FRACTIONNE),
    ("VMA courte", SportSessionType.FRACTIONNE),
    ("Sortie longue", SportSessionType.SORTIE_LONGUE),
    ("Renfo", SportSessionType.RENFORCEMENT),
    ("Vitesse", SportSessionType.VITESSE),
    ("Course à pied", SportSessionType.COURSE),
    ("EF", SportSessionType.EF),
    ("inconnu", SportSessionType.EF),
])
def test_session_type_is_normalized_from_the_screenshot_label(raw, expected):
    assert normalize_session_type(raw) == expected


def test_watch_capture_without_heart_rate_never_touches_the_realised_session(isolate_sqlite_database):
    connector = SqlSportConnector(isolate_sqlite_database)
    connector.log_session(SportSessionCreate(date=date(2026, 10, 8), statut=SportSessionStatus.REALISE,
                                             type_seance=SportSessionType.EF, distance_km=5.0, duree_secondes=1800))
    vision = {"app_source": "Decathlon Connect (CW500 M)", "distance_km": 4.9, "duree_secondes": 1987,
              "fc_moyenne": 0, "fc_max": None}

    with pytest.raises(ScreenshotImportError, match="Aucune fréquence cardiaque lisible"):
        import_screenshot_session(connector, vision, date(2026, 10, 8), "le 8 octobre")

    assert connector.get_all_sessions()[0].distance_km == 5.0


def test_new_session_is_logged_with_a_spoken_confirmation(isolate_sqlite_database):
    connector = SqlSportConnector(isolate_sqlite_database)
    vision = {"app_source": "Strava", "type_seance": "Course", "distance_km": 5.09, "duree_secondes": 1840,
              "denivele_d_plus": 20, "titre": "Course du soir"}

    result = import_screenshot_session(connector, vision, date(2026, 10, 14), "hier")

    assert result["success"] is True and result["session"]["statut"] == "Réalisé"
    assert result["spoken_response"].startswith("Séance Strava hier importée avec succès : 5.09 km en 30 min 40 s (D+ 20 m)")


def test_screenshot_import_has_its_own_router_under_the_sport_prefix():
    from app.routers import sport, sport_screenshot

    assert [r.path for r in sport_screenshot.router.routes] == ["/api/v1/sport/import-screenshot"]
    assert "/api/v1/sport/import-screenshot" not in [r.path for r in sport.router.routes]
    assert callable(sport._call_gemini_coach_tip)  # patché par les tests du tableau de bord
