"""Test d'intégration End-to-End (E2E) de la fiabilisation de l'import de captures sportives.

Rejoue le parcours réel d'une même séance du lundi 12/10/2026 (valeurs extraites des vraies captures) :
1. Séance prévue (Fractionné) dans le carnet.
2. Capture Strava sans date lisible → refus 400 `screenshot_date_missing`, rien n'est enregistré.
3. Renvoi avec la date saisie par l'utilisateur → la séance prévue passe en Réalisé, confirmation datée.
4. Capture Decathlon Coach (FC renvoyée à 0 par Gemini) → mise à jour sans doublon ni erreur 500.
5. Capture Decathlon Connect CW500 M → seule la FC est fusionnée (distance montre ignorée).
6. Panne Gemini Vision → 503 explicite, carnet intact.
"""
from datetime import date
from io import BytesIO
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.connectors.sheets.sport_models import SportSessionType
from app.core.dependencies import set_sport_connector
from app.core.vision.sport_vision_service import VisionServiceUnavailableError


API_HEADERS = {"X-API-Key": "test_key"}
VISION_TARGET = "app.core.vision.sport_vision_service.SportVisionService.analyze_screenshot"
SESSION_DATE = date(2026, 10, 12)

STRAVA_WITHOUT_DATE = {
    "is_sport_session": True, "app_source": "Strava", "date": None, "type_seance": "EF",
    "distance_km": 5.09, "duree_secondes": 1840, "denivele_d_plus": 20, "fc_moyenne": None, "fc_max": None,
}
DECATHLON_COACH = {
    "is_sport_session": True, "app_source": "Decathlon Coach", "date": "2026-10-12", "type_seance": "EF",
    "distance_km": 5.12, "duree_secondes": 1883, "denivele_d_plus": 31, "fc_moyenne": 0, "fc_max": 0,
}
DECATHLON_CONNECT_CW500 = {
    "is_sport_session": True, "app_source": "Decathlon Connect (CW500 M)", "date": "2026-10-12", "type_seance": "EF",
    "distance_km": 4.9, "duree_secondes": 1987, "denivele_d_plus": 0, "fc_moyenne": 163, "fc_max": None,
}


def _upload(client: TestClient, query: str = ""):
    return client.post(
        f"/api/v1/sport/import-screenshot{query}",
        headers=API_HEADERS,
        files={"file": ("capture.jpg", BytesIO(b"fake_image_bytes"), "image/jpeg")},
    )


def _sessions_on(connector: SqlSportConnector, target: date):
    return [s for s in connector.get_all_sessions() if s.date == target]


def test_e2e_screenshot_import_full_journey(isolate_sqlite_database):
    """Scénario complet : date manquante → saisie → Coach → CW500 → panne Gemini, sur une seule séance."""
    connector = SqlSportConnector(db_manager=isolate_sqlite_database)
    set_sport_connector(connector)
    client = TestClient(app)

    try:
        # 1. Séance prévue
        connector.plan_session(
            session_date=SESSION_DATE,
            type_seance=SportSessionType.FRACTIONNE,
            distance_km=5.0,
            programme="Fractionné 10x 30/30",
        )

        with patch(VISION_TARGET) as mock_vision:
            # 2. Capture sans date : refus explicite, rien n'est enregistré
            mock_vision.return_value = dict(STRAVA_WITHOUT_DATE)
            res_missing = _upload(client)
            assert res_missing.status_code == 400
            assert res_missing.headers.get("X-Error-Code") == "screenshot_date_missing"
            assert _sessions_on(connector, SESSION_DATE)[0].statut == "Prévu"

            # 3. Renvoi avec la date saisie : la séance prévue devient réalisée
            mock_vision.return_value = dict(STRAVA_WITHOUT_DATE)
            res_dated = _upload(client, "?reference_date=2026-10-12")
            assert res_dated.status_code == 200
            assert "lundi 12 octobre" in res_dated.json()["spoken_response"]
            session = res_dated.json()["session"]
            assert session["statut"] == "Réalisé"
            assert session["distance_km"] == 5.09
            assert "Fractionné 10x 30/30" in session["programme"]

            # 4. Capture Decathlon Coach (FC à 0) : mise à jour sans doublon ni erreur
            mock_vision.return_value = dict(DECATHLON_COACH)
            res_coach = _upload(client)
            assert res_coach.status_code == 200
            assert res_coach.json()["session"]["distance_km"] == 5.12
            assert res_coach.json()["session"]["fc_moyenne"] is None

            # 5. Capture CW500 : seule la FC est fusionnée
            mock_vision.return_value = dict(DECATHLON_CONNECT_CW500)
            res_cw500 = _upload(client)
            assert res_cw500.status_code == 200
            cw500_session = res_cw500.json()["session"]
            assert cw500_session["fc_moyenne"] == 163
            assert cw500_session["distance_km"] == 5.12
            assert cw500_session["duree_secondes"] == 1883

            # 6. Panne Gemini Vision : 503 explicite
            mock_vision.side_effect = VisionServiceUnavailableError("Tous les modèles Gemini Vision ont échoué : gemini-test (429)")
            res_down = _upload(client)
            assert res_down.status_code == 503
            assert "gemini-test" in res_down.json()["detail"]

        # Bilan : une seule séance réalisée, cohérente et complète
        final_sessions = _sessions_on(connector, SESSION_DATE)
        assert len(final_sessions) == 1
        final = final_sessions[0]
        assert final.statut == "Réalisé"
        assert final.distance_km == 5.12
        assert final.duree_secondes == 1883
        assert final.denivele_d_plus == 31
        assert final.fc_moyenne == 163
    finally:
        set_sport_connector(None)
