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
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import DatabaseManager
from app.core.dependencies import set_database_manager, set_sport_connector
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.connectors.sheets.sport_models import SportSessionType, SportSessionStatus, SportSessionCreate

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
        ("Aujourd'hui à 12:56 · La Rochelle, Charente-Maritime", "2026-10-15"),
        ("Hier à 12:56 · La Rochelle, Charente-Maritime", "2026-10-14"),
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


def test_sport_vision_service_prompt_decathlon_date_guidance():
    """Vérifie que le prompt Gemini Vision inclut le ciblage de date 'JJ/MM/AAAA - HH:MM' sous le titre Decathlon Coach."""
    from app.core.vision.sport_vision_service import SportVisionService
    service = SportVisionService()
    prompt = service.build_prompt(reference_date=date(2026, 10, 15))
    assert "JJ/MM/AAAA" in prompt or "12/10/2026" in prompt
    assert "COURSE À PIED" in prompt
    assert "date" in prompt


def test_import_screenshot_without_date_protects_existing_realised_session(temp_sport_env):
    """Vérifie qu'un screenshot sans date détectée ne vient JAMAIS écraser une séance déjà réalisée."""
    db_mgr, connector = temp_sport_env

    # 1. Séance existante déjà réalisée aujourd'hui
    today = date.today()
    existing_session = connector.log_session(
        SportSessionCreate(
            date=today,
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.COURSE,
            distance_km=6.01,
            duree_secondes=2132,
            remarques="Remarques précieuses de l'utilisateur à ne pas écraser",
        )
    )

    # 2. Capture dont la date n'a pas pu être extraite (date = None)
    fake_vision_result = {
        "is_sport_session": True,
        "app_source": "Decathlon Coach",
        "date": None,
        "type_seance": "Course",
        "distance_km": 5.12,
        "duree_secondes": 1883,
        "titre": "COURSE À PIED",
    }
    fake_image_file = BytesIO(b"fake_bytes")

    with patch("app.core.vision.sport_vision_service.SportVisionService.analyze_screenshot") as mock_vision:
        mock_vision.return_value = fake_vision_result

        response = client.post(
            "/api/v1/sport/import-screenshot",
            headers=API_HEADERS,
            files={"file": ("screenshot.jpg", fake_image_file, "image/jpeg")},
        )

        # Doit être rejeté pour protéger les données
        assert response.status_code == 400
        assert "protéger vos données" in response.json()["detail"].lower() or "séance réalisée existe déjà" in response.json()["detail"].lower()

    # 3. Vérifier que la séance originale d'aujourd'hui est restée STRICTEMENT intacte
    fresh_session = connector.get_session(today)
    assert fresh_session.distance_km == 6.01
    assert fresh_session.duree_secondes == 2132
    assert "Remarques précieuses" in fresh_session.remarques


def test_import_screenshot_with_different_realised_creates_distinct_session(temp_sport_env):
    """Vérifie qu'un screenshot à une date où une séance réalisée différente existe ne l'écrase pas mais crée une session distincte."""
    db_mgr, connector = temp_sport_env

    # 1. Séance existante déjà réalisée le 12 octobre
    connector.log_session(
        SportSessionCreate(
            date=date(2026, 10, 12),
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.SORTIE_LONGUE,
            distance_km=10.0,
            duree_secondes=3600,
            remarques="Course du matin",
        )
    )

    # 2. Capture avec date explicite 12/10/2026 mais séance différente (5.12 km)
    fake_vision_result = {
        "is_sport_session": True,
        "app_source": "Decathlon Coach",
        "date": "2026-10-12",
        "type_seance": "Course",
        "distance_km": 5.12,
        "duree_secondes": 1883,
        "titre": "COURSE À PIED",
    }
    fake_image_file = BytesIO(b"fake_bytes")

    with patch("app.core.vision.sport_vision_service.SportVisionService.analyze_screenshot") as mock_vision:
        mock_vision.return_value = fake_vision_result

        response = client.post(
            "/api/v1/sport/import-screenshot",
            headers=API_HEADERS,
            files={"file": ("screenshot.jpg", fake_image_file, "image/jpeg")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session"]["distance_km"] == 5.12

    # Vérifier que les deux séances coexistent dans la base pour le 12/10
    sessions_12 = [s for s in connector.get_all_sessions() if s.date == date(2026, 10, 12)]
    assert len(sessions_12) == 2
    distances = {s.distance_km for s in sessions_12}
    assert 10.0 in distances
    assert 5.12 in distances


def test_gemini_sport_vision_schema_requires_essential_metrics():
    """Vérifie que le schéma JSON pour Gemini Vision force la présence de date, distance_km et duree_secondes."""
    from app.core.vision.sport_vision_service import GEMINI_SPORT_VISION_SCHEMA

    required = GEMINI_SPORT_VISION_SCHEMA.get("required", [])
    assert "is_sport_session" in required
    assert "app_source" in required
    assert "date" in required, "Le champ 'date' doit être impérativement dans required pour forcer Gemini à l'extraire"
    assert "distance_km" in required, "Le champ 'distance_km' doit être requis"
    assert "duree_secondes" in required, "Le champ 'duree_secondes' doit être requis"





def test_gemini_sport_vision_schema_allows_null_for_unreadable_metrics():
    """Vérifie que date, distance_km et duree_secondes acceptent null pour ne jamais forcer Gemini à inventer une valeur."""
    from app.core.vision.sport_vision_service import GEMINI_SPORT_VISION_SCHEMA

    props = GEMINI_SPORT_VISION_SCHEMA["properties"]
    for field in ("date", "distance_km", "duree_secondes"):
        assert props[field].get("nullable") is True, f"Le champ '{field}' doit être nullable"


def _make_vision_client(api_key: str = "fake_key") -> MagicMock:
    fake_client = MagicMock()
    fake_client.api_key = api_key
    fake_client.get_candidate_models.return_value = ["gemini-test-flash"]
    fake_client.premium_candidate_models = AsyncMock(return_value=["gemini-test-flash"])
    return fake_client


@pytest.mark.asyncio
async def test_analyze_screenshot_raises_explicit_error_without_api_key():
    """Vérifie qu'une clé Gemini absente lève une erreur explicite au lieu d'un faux rejet 'image non sportive'."""
    from app.core.vision.sport_vision_service import SportVisionService, VisionServiceUnavailableError

    service = SportVisionService(gemini_client=_make_vision_client(api_key=""))
    with pytest.raises(VisionServiceUnavailableError, match="GEMINI_API_KEY"):
        await service.analyze_screenshot(image_bytes=b"img", reference_date=date(2026, 10, 15))


@pytest.mark.asyncio
async def test_analyze_screenshot_raises_explicit_error_when_all_models_fail():
    """Vérifie que l'échec de tous les modèles lève une erreur listant les modèles tentés et la dernière erreur."""
    from app.core.vision.sport_vision_service import SportVisionService, VisionServiceUnavailableError

    service = SportVisionService(gemini_client=_make_vision_client())
    error_response = MagicMock(status_code=500, text="Internal error")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = error_response
        with pytest.raises(VisionServiceUnavailableError) as exc_info:
            await service.analyze_screenshot(image_bytes=b"img", reference_date=date(2026, 10, 15))

    message = str(exc_info.value)
    assert "gemini-test-flash" in message
    assert "500" in message


@pytest.mark.asyncio
async def test_analyze_screenshot_keeps_null_date_when_not_visible():
    """Vérifie qu'une date null renvoyée par Gemini n'est pas remplacée par la date du jour dans le service."""
    import json
    from app.core.vision.sport_vision_service import SportVisionService

    service = SportVisionService(gemini_client=_make_vision_client())
    payload = {"is_sport_session": True, "app_source": "Strava", "date": None, "distance_km": 5.0, "duree_secondes": 1800}
    ok_response = MagicMock(status_code=200)
    ok_response.json.return_value = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = ok_response
        result = await service.analyze_screenshot(image_bytes=b"img", reference_date=date(2026, 10, 15))

    assert result["date"] is None
    assert result["distance_km"] == 5.0


def test_import_screenshot_returns_503_when_vision_unavailable(temp_sport_env):
    """Vérifie qu'une panne Gemini Vision remonte en 503 explicite (et non en rejet 400 'image non sportive')."""
    from app.core.vision.sport_vision_service import VisionServiceUnavailableError

    with patch("app.core.vision.sport_vision_service.SportVisionService.analyze_screenshot") as mock_vision:
        mock_vision.side_effect = VisionServiceUnavailableError("Tous les modèles Gemini Vision ont échoué : gemini-test-flash (429)")

        response = client.post(
            "/api/v1/sport/import-screenshot",
            headers=API_HEADERS,
            files={"file": ("screenshot.jpg", BytesIO(b"fake_bytes"), "image/jpeg")},
        )

    assert response.status_code == 503
    assert "gemini-test-flash" in response.json()["detail"]


def test_import_screenshot_without_date_never_defaults_to_today(temp_sport_env):
    """Vérifie qu'une capture sans date lisible n'est jamais enregistrée à la date du jour, même sans séance existante."""
    db_mgr, connector = temp_sport_env

    fake_vision_result = {
        "is_sport_session": True,
        "app_source": "Decathlon Coach",
        "date": None,
        "type_seance": "Course",
        "distance_km": 5.12,
        "duree_secondes": 1883,
        "titre": "COURSE À PIED",
    }

    with patch("app.core.vision.sport_vision_service.SportVisionService.analyze_screenshot") as mock_vision:
        mock_vision.return_value = fake_vision_result

        response = client.post(
            "/api/v1/sport/import-screenshot",
            headers=API_HEADERS,
            files={"file": ("screenshot.jpg", BytesIO(b"fake_bytes"), "image/jpeg")},
        )

    assert response.status_code == 400
    detail = response.json()["detail"].lower()
    assert "date" in detail
    assert "ne semble pas être une capture" not in detail
    assert connector.get_all_sessions() == []


def test_import_screenshot_without_date_uses_explicit_reference_date(temp_sport_env):
    """Vérifie qu'une date fournie explicitement par l'utilisateur (reference_date) est utilisée quand la capture n'en contient pas."""
    fake_vision_result = {
        "is_sport_session": True,
        "app_source": "Decathlon Coach",
        "date": None,
        "type_seance": "Course",
        "distance_km": 5.12,
        "duree_secondes": 1883,
        "titre": "COURSE À PIED",
    }

    with patch("app.core.vision.sport_vision_service.SportVisionService.analyze_screenshot") as mock_vision:
        mock_vision.return_value = fake_vision_result

        response = client.post(
            "/api/v1/sport/import-screenshot?reference_date=2026-10-12",
            headers=API_HEADERS,
            files={"file": ("screenshot.jpg", BytesIO(b"fake_bytes"), "image/jpeg")},
        )

    assert response.status_code == 200
    assert response.json()["session"]["date"] == "2026-10-12"


def _cw500_vision_result(fc_moyenne=163):
    return {
        "is_sport_session": True,
        "app_source": "Decathlon Connect (CW500 M)",
        "date": "2026-10-12",
        "type_seance": "EF",
        "distance_km": 4.9,
        "duree_secondes": 1987,
        "fc_moyenne": fc_moyenne,
        "fc_max": None,
        "cadence_spm": 170,
        "titre": "Course à pied",
    }


def test_import_cw500_on_existing_realised_session_only_merges_heart_rate(temp_sport_env):
    """Vérifie qu'une capture CW500 complète uniquement la FC d'une séance déjà réalisée (distance/durée de la montre non fiables)."""
    db_mgr, connector = temp_sport_env
    connector.log_session(
        SportSessionCreate(
            date=date(2026, 10, 12),
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.FRACTIONNE,
            distance_km=5.12,
            duree_secondes=1883,
            denivele_d_plus=31,
            remarques="Bonnes sensations",
        )
    )

    with patch("app.core.vision.sport_vision_service.SportVisionService.analyze_screenshot") as mock_vision:
        mock_vision.return_value = _cw500_vision_result()

        response = client.post(
            "/api/v1/sport/import-screenshot",
            headers=API_HEADERS,
            files={"file": ("screenshot_cw500.jpg", BytesIO(b"fake_bytes"), "image/jpeg")},
        )

    assert response.status_code == 200
    saved = response.json()["session"]
    assert saved["fc_moyenne"] == 163
    assert saved["distance_km"] == 5.12
    assert saved["duree_secondes"] == 1883
    assert saved["denivele_d_plus"] == 31
    assert saved["type_seance"] == "Fractionné"
    assert "Bonnes sensations" in saved["remarques"]
    assert "163" in response.json()["spoken_response"]

    sessions_12 = [s for s in connector.get_all_sessions() if s.date == date(2026, 10, 12)]
    assert len(sessions_12) == 1, "Aucun doublon ne doit être créé par l'import CW500"


def test_import_cw500_without_heart_rate_on_existing_session_is_rejected(temp_sport_env):
    """Vérifie qu'une capture CW500 sans FC lisible sur une séance existante est rejetée explicitement sans rien modifier."""
    db_mgr, connector = temp_sport_env
    connector.log_session(
        SportSessionCreate(
            date=date(2026, 10, 12),
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.EF,
            distance_km=5.12,
            duree_secondes=1883,
        )
    )

    with patch("app.core.vision.sport_vision_service.SportVisionService.analyze_screenshot") as mock_vision:
        mock_vision.return_value = _cw500_vision_result(fc_moyenne=None)

        response = client.post(
            "/api/v1/sport/import-screenshot",
            headers=API_HEADERS,
            files={"file": ("screenshot_cw500.jpg", BytesIO(b"fake_bytes"), "image/jpeg")},
        )

    assert response.status_code == 400
    assert "fréquence cardiaque" in response.json()["detail"].lower()
    sessions_12 = [s for s in connector.get_all_sessions() if s.date == date(2026, 10, 12)]
    assert len(sessions_12) == 1
    assert sessions_12[0].fc_moyenne is None


def test_import_cw500_on_planned_session_marks_realised_with_duration_and_heart_rate_only(temp_sport_env):
    """Vérifie qu'une capture CW500 sur une séance prévue la passe en Réalisé avec durée + FC, sans importer la distance de la montre."""
    db_mgr, connector = temp_sport_env
    connector.plan_session(
        session_date=date(2026, 10, 12),
        type_seance=SportSessionType.FRACTIONNE,
        distance_km=6.0,
        programme="Fractionné 10x 30/30",
    )

    with patch("app.core.vision.sport_vision_service.SportVisionService.analyze_screenshot") as mock_vision:
        mock_vision.return_value = _cw500_vision_result()

        response = client.post(
            "/api/v1/sport/import-screenshot",
            headers=API_HEADERS,
            files={"file": ("screenshot_cw500.jpg", BytesIO(b"fake_bytes"), "image/jpeg")},
        )

    assert response.status_code == 200
    saved = response.json()["session"]
    assert saved["statut"] == "Réalisé"
    assert saved["duree_secondes"] == 1987
    assert saved["fc_moyenne"] == 163
    assert saved["distance_km"] != 4.9, "La distance CW500 n'est pas fiable et ne doit pas être importée"
    assert saved["type_seance"] == "Fractionné"
    assert "Fractionné 10x 30/30" in saved["programme"]

    sessions_12 = [s for s in connector.get_all_sessions() if s.date == date(2026, 10, 12)]
    assert len(sessions_12) == 1


def test_import_screenshot_zero_heart_rate_never_overwrites_existing_value(temp_sport_env):
    """Vérifie qu'une FC à 0 renvoyée par Gemini (valeur absente de la capture) n'écrase jamais une FC existante."""
    db_mgr, connector = temp_sport_env
    connector.log_session(
        SportSessionCreate(
            date=date(2026, 10, 12),
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.EF,
            distance_km=5.12,
            duree_secondes=1883,
            fc_moyenne=163,
        )
    )

    fake_vision_result = {
        "is_sport_session": True,
        "app_source": "Decathlon Coach",
        "date": "2026-10-12",
        "type_seance": "EF",
        "distance_km": 5.12,
        "duree_secondes": 1883,
        "denivele_d_plus": 31,
        "fc_moyenne": 0,
        "fc_max": 0,
        "titre": "Course à pied",
    }

    with patch("app.core.vision.sport_vision_service.SportVisionService.analyze_screenshot") as mock_vision:
        mock_vision.return_value = fake_vision_result

        response = client.post(
            "/api/v1/sport/import-screenshot",
            headers=API_HEADERS,
            files={"file": ("screenshot_coach.jpg", BytesIO(b"fake_bytes"), "image/jpeg")},
        )

    assert response.status_code == 200
    saved = response.json()["session"]
    assert saved["fc_moyenne"] == 163
    assert saved["fc_max"] is None


def test_import_cw500_zero_max_heart_rate_is_ignored(temp_sport_env):
    """Vérifie qu'une FC max à 0 sur une capture CW500 n'est pas enregistrée."""
    db_mgr, connector = temp_sport_env
    connector.log_session(
        SportSessionCreate(
            date=date(2026, 10, 12),
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.EF,
            distance_km=5.12,
            duree_secondes=1883,
        )
    )
    cw500 = _cw500_vision_result()
    cw500["fc_max"] = 0

    with patch("app.core.vision.sport_vision_service.SportVisionService.analyze_screenshot") as mock_vision:
        mock_vision.return_value = cw500

        response = client.post(
            "/api/v1/sport/import-screenshot",
            headers=API_HEADERS,
            files={"file": ("screenshot_cw500.jpg", BytesIO(b"fake_bytes"), "image/jpeg")},
        )

    assert response.status_code == 200
    saved = response.json()["session"]
    assert saved["fc_moyenne"] == 163
    assert saved["fc_max"] is None
    assert "max" not in response.json()["spoken_response"]


def test_gemini_sport_vision_schema_allows_null_heart_rate():
    """Vérifie que les FC acceptent null pour que Gemini ne renvoie pas 0 quand elles sont absentes."""
    from app.core.vision.sport_vision_service import GEMINI_SPORT_VISION_SCHEMA

    props = GEMINI_SPORT_VISION_SCHEMA["properties"]
    for field in ("fc_moyenne", "fc_max"):
        assert props[field].get("nullable") is True, f"Le champ '{field}' doit être nullable"


def test_import_screenshot_without_date_exposes_machine_readable_error_code(temp_sport_env):
    """Vérifie que le refus pour date manquante expose un code d'erreur stable (X-Error-Code) exploitable par le frontend."""
    fake_vision_result = {
        "is_sport_session": True,
        "app_source": "Decathlon Coach",
        "date": None,
        "distance_km": 5.12,
        "duree_secondes": 1883,
    }

    with patch("app.core.vision.sport_vision_service.SportVisionService.analyze_screenshot") as mock_vision:
        mock_vision.return_value = fake_vision_result

        response = client.post(
            "/api/v1/sport/import-screenshot",
            headers=API_HEADERS,
            files={"file": ("screenshot.jpg", BytesIO(b"fake_bytes"), "image/jpeg")},
        )

    assert response.status_code == 400
    assert response.headers.get("X-Error-Code") == "screenshot_date_missing"


def test_import_screenshot_without_date_and_realised_today_exposes_same_error_code(temp_sport_env):
    """Vérifie que le garde-fou 'séance réalisée aujourd'hui' expose aussi le code screenshot_date_missing."""
    db_mgr, connector = temp_sport_env
    connector.log_session(
        SportSessionCreate(
            date=date.today(),
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.EF,
            distance_km=6.0,
            duree_secondes=2100,
        )
    )
    fake_vision_result = {
        "is_sport_session": True,
        "app_source": "Decathlon Coach",
        "date": None,
        "distance_km": 5.12,
        "duree_secondes": 1883,
    }

    with patch("app.core.vision.sport_vision_service.SportVisionService.analyze_screenshot") as mock_vision:
        mock_vision.return_value = fake_vision_result

        response = client.post(
            "/api/v1/sport/import-screenshot",
            headers=API_HEADERS,
            files={"file": ("screenshot.jpg", BytesIO(b"fake_bytes"), "image/jpeg")},
        )

    assert response.status_code == 400
    assert response.headers.get("X-Error-Code") == "screenshot_date_missing"


@pytest.mark.parametrize(
    "vision_result,existing",
    [
        ({"app_source": "Strava", "distance_km": 5.09, "duree_secondes": 1840}, None),
        ({"app_source": "Decathlon Connect (CW500 M)", "distance_km": 4.9, "duree_secondes": 1987, "fc_moyenne": 163}, "realise"),
        ({"app_source": "Decathlon Connect (CW500 M)", "distance_km": 4.9, "duree_secondes": 1987, "fc_moyenne": 163}, "prevu"),
    ],
)
def test_import_screenshot_confirmation_states_retained_date(temp_sport_env, vision_result, existing):
    """Vérifie que la confirmation vocale annonce explicitement la date retenue, quel que soit le chemin d'import."""
    db_mgr, connector = temp_sport_env
    if existing == "realise":
        connector.log_session(
            SportSessionCreate(
                date=date(2026, 10, 12),
                statut=SportSessionStatus.REALISE,
                type_seance=SportSessionType.EF,
                distance_km=5.12,
                duree_secondes=1883,
            )
        )
    elif existing == "prevu":
        connector.plan_session(session_date=date(2026, 10, 12), type_seance=SportSessionType.EF, distance_km=5.0)

    payload = {"is_sport_session": True, "date": "2026-10-12", "type_seance": "EF", **vision_result}

    with patch("app.core.vision.sport_vision_service.SportVisionService.analyze_screenshot") as mock_vision:
        mock_vision.return_value = payload

        response = client.post(
            "/api/v1/sport/import-screenshot",
            headers=API_HEADERS,
            files={"file": ("screenshot.jpg", BytesIO(b"fake_bytes"), "image/jpeg")},
        )

    assert response.status_code == 200
    assert "lundi 12 octobre" in response.json()["spoken_response"]
