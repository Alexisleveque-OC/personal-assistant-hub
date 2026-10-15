"""Tests TDD pour l'Étape 3.1 : Import de séances par Capture d'Écran (Gemini Vision) & Observabilité UI.

Couvre :
1. Modèle et extraction de SportScreenshotAnalysisResult pour les 3 formats :
   - Format 1 : Strava (distance 5.09 km, durée 30:40, allure 6:01/km, D+ 20m, date relative)
   - Format 2 : Decathlon Coach (distance 5.12 km, durée 31'23", D+ 31m, allure 06'07"/km, date 12/10/2026)
   - Format 3 : Decathlon Connect CW500 M (distance 4.9 km, durée 33:07, FC moy 163 bpm, cadence 170, date 08/10/2026)
2. Endpoint POST /api/v1/sport/import-screenshot :
   - Ingestion d'une capture d'écran
   - Déduplication et adaptation d'une séance planifiée existante vers Réalisé
   - Recalcul immédiat de la synthèse hebdomadaire
   - Réponse vocale contextualisée d'Otis
3. Observabilité et gestion d'erreurs :
   - Image non sportive rejetée avec message explicite (pas d'échec muet)
   - Erreur API Gemini contextualisée
"""
from datetime import date
from io import BytesIO
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import DatabaseManager
from app.core.dependencies import set_database_manager, set_sport_connector
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.connectors.sheets.sport_models import SportSessionType, SportSessionStatus

client = TestClient(app)
API_HEADERS = {"X-API-Key": "test_api_key"}


@pytest.fixture
def temp_sport_env(tmp_path):
    """Initialise une base SQLite temporaire et un connecteur sport actif."""
    db_file = tmp_path / "test_sport_vision.db"
    db_mgr = DatabaseManager(db_path=str(db_file))
    db_mgr.init_db()
    set_database_manager(db_mgr)
    connector = SqlSportConnector(db_mgr)
    set_sport_connector(connector)
    yield db_mgr, connector
    set_database_manager(None)
    set_sport_connector(None)


def test_import_screenshot_decathlon_coach_format(temp_sport_env):
    """Vérifie l'ingestion d'une capture Decathlon Coach (Format 2: 5.12 km, 31'23\", D+ 31m, 12/10/2026)."""
    db_mgr, connector = temp_sport_env

    # 1. Séance préalablement planifiée pour le 12 octobre 2026
    connector.plan_session(
        session_date=date(2026, 10, 12),
        type_seance=SportSessionType.FRACTIONNE,
        distance_km=5.0,
        programme="Fractionné 10x 30/30",
    )

    fake_vision_result = {
        "is_sport_session": True,
        "app_source": "Decathlon Coach",
        "date": "2026-10-12",
        "heure_depart": "12:55",
        "type_seance": "Fractionné",
        "distance_km": 5.12,
        "duree_secondes": 1883,  # 31 min 23 sec
        "denivele_d_plus": 31,
        "allure_moyenne": "06:07",
        "vitesse_kmh": 9.79,
        "calories_kcal": 517,
        "fc_moyenne": None,
        "fc_max": None,
        "cadence_spm": None,
        "titre": "Course à pied",
    }

    fake_image_file = BytesIO(b"fake_decathlon_coach_image_bytes")

    with patch("app.core.vision.sport_vision_service.SportVisionService.analyze_screenshot") as mock_vision:
        mock_vision.return_value = fake_vision_result

        response = client.post(
            "/api/v1/sport/import-screenshot",
            headers=API_HEADERS,
            files={"file": ("screenshot_decathlon.jpg", fake_image_file, "image/jpeg")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["app_source"] == "Decathlon Coach"

        # Vérification des métriques enregistrées
        saved_session = data["session"]
        assert saved_session["distance_km"] == 5.12
        assert saved_session["duree_secondes"] == 1883
        assert saved_session["denivele_d_plus"] == 31
        assert saved_session["statut"] == "Réalisé"
        # Le programme technique initial doit être préservé
        assert "Fractionné 10x 30/30" in saved_session["programme"]
        # Vérification du recalcul automatique
        assert saved_session["allure_formatted"] in ("06:07", "06:08")
        assert saved_session["vitesse_kmh"] == 9.79

        # Confirmation vocale conviviale d'Otis
        spoken = data["spoken_response"]
        assert "5,12" in spoken or "5.12" in spoken
        assert "31" in spoken


def test_import_screenshot_decathlon_connect_cw500_heart_rate(temp_sport_env):
    """Vérifie l'ingestion d'une capture Decathlon Connect CW500 M avec FC 163 bpm (Format 3)."""
    db_mgr, connector = temp_sport_env

    fake_vision_result = {
        "is_sport_session": True,
        "app_source": "Decathlon Connect (CW500 M)",
        "date": "2026-10-08",
        "heure_depart": "13:05",
        "type_seance": "EF",
        "distance_km": 4.9,
        "duree_secondes": 1987,  # 33 min 7 sec
        "denivele_d_plus": 0,
        "allure_moyenne": "06:43",
        "vitesse_kmh": 8.9,
        "calories_kcal": 307,
        "fc_moyenne": 163,
        "fc_max": None,
        "cadence_spm": 170,
        "titre": "Course à pied",
    }

    fake_image_file = BytesIO(b"fake_cw500_image_bytes")

    with patch("app.core.vision.sport_vision_service.SportVisionService.analyze_screenshot") as mock_vision:
        mock_vision.return_value = fake_vision_result

        response = client.post(
            "/api/v1/sport/import-screenshot",
            headers=API_HEADERS,
            files={"file": ("screenshot_cw500.jpg", fake_image_file, "image/jpeg")},
        )

        assert response.status_code == 200
        data = response.json()
        saved = data["session"]
        assert saved["distance_km"] == 4.9
        assert saved["duree_secondes"] == 1987
        assert saved["fc_moyenne"] == 163
        assert saved["statut"] == "Réalisé"
        assert "163" in data["spoken_response"]


def test_import_screenshot_strava_relative_date(temp_sport_env):
    """Vérifie l'ingestion d'une capture Strava avec date relative résolue (Format 1)."""
    db_mgr, connector = temp_sport_env

    fake_vision_result = {
        "is_sport_session": True,
        "app_source": "Strava",
        "date": "2026-10-12",  # Résolu
        "heure_depart": "12:56",
        "type_seance": "EF",
        "distance_km": 5.09,
        "duree_secondes": 1840,  # 30 min 40 sec
        "denivele_d_plus": 20,
        "allure_moyenne": "06:01",
        "vitesse_kmh": 9.96,
        "calories_kcal": None,
        "fc_moyenne": None,
        "fc_max": None,
        "cadence_spm": None,
        "titre": "Course à pied du midi",
    }

    fake_image_file = BytesIO(b"fake_strava_image_bytes")

    with patch("app.core.vision.sport_vision_service.SportVisionService.analyze_screenshot") as mock_vision:
        mock_vision.return_value = fake_vision_result

        response = client.post(
            "/api/v1/sport/import-screenshot",
            headers=API_HEADERS,
            files={"file": ("screenshot_strava.jpg", fake_image_file, "image/jpeg")},
        )

        assert response.status_code == 200
        data = response.json()
        saved = data["session"]
        assert saved["distance_km"] == 5.09
        assert saved["duree_secondes"] == 1840
        assert saved["denivele_d_plus"] == 20


def test_import_screenshot_rejects_non_sport_image(temp_sport_env):
    """Vérifie le rejet explicite d'une image ne contenant pas de séance sportive."""
    fake_vision_result = {
        "is_sport_session": False,
        "app_source": "Inconnu",
        "titre": "Photo de paysage",
        "message": "Cette image ne contient aucun récapitulatif de séance sportive.",
    }

    fake_image_file = BytesIO(b"fake_cat_photo_bytes")

    with patch("app.core.vision.sport_vision_service.SportVisionService.analyze_screenshot") as mock_vision:
        mock_vision.return_value = fake_vision_result

        response = client.post(
            "/api/v1/sport/import-screenshot",
            headers=API_HEADERS,
            files={"file": ("cat.jpg", fake_image_file, "image/jpeg")},
        )

        assert response.status_code == 400
        data = response.json()
        assert "sportive" in data["detail"].lower() or "sport" in data["detail"].lower()


@pytest.mark.parametrize(
    "raw_date_input,expected_date_str",
    [
        ("12/10/2026", "2026-10-12"),
        ("12/10/2026 - 12:55", "2026-10-12"),
        ("2026-10-12T12:55:00", "2026-10-12"),
        ("08 oct. 2026", "2026-10-08"),
        ("8 octobre 2026", "2026-10-08"),
        ("2026-10-12", "2026-10-12"),
        ("14/10", "2026-10-14"),
        ("14/10 à 18:30", "2026-10-14"),
        ("14 oct.", "2026-10-14"),
        ("Mercredi 14", "2026-10-14"),
        ("mercredi", "2026-10-14"),
        ("Hier", "2026-10-14"),
    ],
)
def test_import_screenshot_date_formats_resilience(temp_sport_env, raw_date_input, expected_date_str):
    """Vérifie que les formats de dates réels variés des captures sont résolus sans fallback sur aujourd'hui."""
    db_mgr, connector = temp_sport_env

    fake_vision_result = {
        "is_sport_session": True,
        "app_source": "Decathlon Coach",
        "date": raw_date_input,
        "heure_depart": "12:55",
        "type_seance": "EF",
        "distance_km": 5.12,
        "duree_secondes": 1883,
        "denivele_d_plus": 31,
        "allure_moyenne": "06:07",
        "titre": "Course à pied",
    }

    fake_image_file = BytesIO(b"fake_decathlon_bytes")

    with patch("app.core.vision.sport_vision_service.SportVisionService.analyze_screenshot") as mock_vision:
        mock_vision.return_value = fake_vision_result

        response = client.post(
            "/api/v1/sport/import-screenshot?reference_date=2026-10-15",
            headers=API_HEADERS,
            files={"file": ("screenshot.jpg", fake_image_file, "image/jpeg")},
        )

        assert response.status_code == 200
        data = response.json()
        saved = data["session"]
        assert saved["date"] == expected_date_str

