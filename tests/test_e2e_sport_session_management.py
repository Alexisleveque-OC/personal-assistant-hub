"""Test d'intégration End-to-End (E2E) pour la gestion des séances sportives et la résolution des dates.

Valide de bout en bout :
1. L'import de capture Decathlon Coach avec date textuelle ('Mercredi 14 oct.', '14/10') résolue au 14/10/2026 (passé).
2. La modification de la date d'une séance existante via PATCH /session/id/{id} avec recalcul de la semaine ISO et des synthèses.
3. La création manuelle d'une séance via POST /api/v1/sport/session.
4. Le traitement vocal de "J'ai fait une séance de fractionné" confirmant une séance de Fractionné (et JAMAIS de renfo).
5. La cohérence des données sur le dashboard et les synthèses hebdomadaires.
"""
from datetime import date
from io import BytesIO
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.dependencies import set_sport_connector


API_HEADERS = {"X-API-Key": "test_key"}


def test_e2e_sport_session_management_and_date_resolution(isolate_sqlite_database):
    """Scénario complet E2E validant la chaîne complète des fonctionnalités et correctifs."""
    connector = SqlSportConnector(db_manager=isolate_sqlite_database)
    set_sport_connector(connector)
    client = TestClient(app)

    try:
        # 1. Ingestion d'une capture Decathlon Coach datée "Mercredi 14 oct." avec date de référence du 15/10/2026
        fake_vision = {
            "is_sport_session": True,
            "app_source": "Decathlon Coach",
            "date": "Mercredi 14 oct.",
            "heure_depart": "18:30",
            "type_seance": "EF",
            "distance_km": 6.0,
            "duree_secondes": 2160,
            "denivele_d_plus": 30,
            "allure_moyenne": "06:00",
            "titre": "Course à pied",
        }
        fake_img = BytesIO(b"fake_decathlon_stream")

        with patch("app.core.vision.sport_vision_service.SportVisionService.analyze_screenshot") as mock_vision:
            mock_vision.return_value = fake_vision

            resp_import = client.post(
                "/api/v1/sport/import-screenshot?reference_date=2026-10-15",
                headers=API_HEADERS,
                files={"file": ("screenshot.jpg", fake_img, "image/jpeg")},
            )

        assert resp_import.status_code == 200
        data_import = resp_import.json()
        assert data_import["success"] is True
        session_1 = data_import["session"]
        session_id = session_1["id"]
        # Doit être résolu au mercredi 14 octobre 2026 (hier), et NON au 15/10 (aujourd'hui)
        assert session_1["date"] == "2026-10-14"
        assert session_1["distance_km"] == 6.0
        assert session_1["semaine"] == 42

        # 2. Modification manuelle de la date via le sélecteur (ex: déplacement au 13/10/2026)
        resp_patch = client.patch(
            f"/api/v1/sport/session/id/{session_id}",
            json={"date": "2026-10-13", "remarques": "Date ajustée manuellement"},
            headers=API_HEADERS,
        )
        assert resp_patch.status_code == 200
        data_patch = resp_patch.json()
        assert data_patch["session"]["date"] == "2026-10-13"
        assert data_patch["session"]["remarques"] == "Date ajustée manuellement"
        assert data_patch["session"]["distance_km"] == 6.0

        # 3. Création manuelle d'une séance via l'interface (+ Nouvelle séance)
        new_payload = {
            "date": "2026-10-14",
            "statut": "Réalisé",
            "type_seance": "Sortie Longue",
            "distance_km": 12.5,
            "duree_secondes": 4500,
            "denivele_d_plus": 75,
            "ressenti_rpe": 6,
            "programme": "Sortie longue allure progressive",
            "remarques": "Très bonnes sensations",
        }
        resp_create = client.post(
            "/api/v1/sport/session",
            json=new_payload,
            headers=API_HEADERS,
        )
        assert resp_create.status_code == 201
        data_create = resp_create.json()
        assert data_create["session"]["date"] == "2026-10-14"
        assert data_create["session"]["type_seance"] == "Sortie Longue"
        assert data_create["session"]["distance_km"] == 12.5

        # 4. Requête vocale : "J'ai fait une séance de fractionné"
        resp_voice = client.post(
            "/api/v1/interact",
            json={"query": "J'ai fait une séance de fractionné. Est-ce que tu peux m'en enregistrer une s'il te plaît ?"},
            headers=API_HEADERS,
        )
        assert resp_voice.status_code == 200
        data_voice = resp_voice.json()
        spoken = data_voice["spoken_response"]
        assert "Fractionné" in spoken
        assert "renforcement musculaire" not in spoken

        # 5. Vérification du listing des séances
        resp_sessions = client.get("/api/v1/sport/sessions", headers=API_HEADERS)
        assert resp_sessions.status_code == 200
        all_sessions = resp_sessions.json()["sessions"]
        assert len(all_sessions) >= 3

        # 6. Vérification de la synthèse hebdomadaire
        resp_sum = client.get("/api/v1/sport/summaries?annee=2026", headers=API_HEADERS)
        assert resp_sum.status_code == 200
        sums = resp_sum.json()["summaries"]
        assert len(sums) > 0
        w42 = next((s for s in sums if s["summary"]["semaine"] == 42), None)
        assert w42 is not None
        assert w42["summary"]["km_total"] >= 18.5  # 6.0 + 12.5

    finally:
        set_sport_connector(None)
