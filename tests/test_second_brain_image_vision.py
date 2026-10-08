"""Tests unitaires et d'intégration pour l'ingestion multimodale d'images (Screenshots/Photos)

vers le Second Cerveau via Gemini Vision.
TDD Phase Rouge -> Phase Verte.
"""
import io
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import get_database_manager
from app.core.models import SecondBrainImageAnalysisResult


@pytest.fixture
def mock_vision_gemini_analysis():
    """Simule la réponse structurée renvoyée par Gemini Flash Vision."""
    return SecondBrainImageAnalysisResult(
        category="bug_report",
        title="Erreur 500 dans la console sur /api/v1/users",
        summary="Capture d'écran de l'inspecteur Chrome montrant une StackTrace Python 'KeyError: user_id' lors de l'appel POST /api/v1/users.",
        tags=["bug", "api", "console", "python"],
        suggested_action="Vérifier la clé 'user_id' dans le payload de requête.",
    )


def test_analyze_image_for_second_brain_unit(mock_vision_gemini_analysis):
    """Vérifie le service d'analyse d'image sans appel réseau direct."""
    from app.core.vision.vision_service import analyze_image_for_second_brain

    fake_image_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" # Header PNG valide

    with patch("app.core.vision.vision_service._call_gemini_vision") as mock_gemini:
        mock_gemini.return_value = mock_vision_gemini_analysis

        result = analyze_image_for_second_brain(
            image_bytes=fake_image_bytes,
            mime_type="image/png",
            user_caption="J'ai trouvé ce bug en testant le profil",
        )

        assert result.category == "bug_report"
        assert "Erreur 500" in result.title
        assert "KeyError" in result.summary
        assert "bug" in result.tags
        mock_gemini.assert_called_once()


def test_api_upload_screenshot_creates_note_and_audit_log(mock_vision_gemini_analysis):
    """Vérifie que l'endpoint POST /api/v1/second-brain/notes/image analyse l'image,

    persiste la note en base SQLite et crée un log d'audit.
    """
    client = TestClient(app)
    db = get_database_manager()
    db.init_db()

    fake_file = io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRfakeimagedata")

    with patch("app.routers.second_brain.analyze_image_for_second_brain") as mock_analyze:
        mock_analyze.return_value = mock_vision_gemini_analysis

        response = client.post(
            "/api/v1/second-brain/notes/image",
            files={"image": ("screenshot.png", fake_file, "image/png")},
            data={"caption": "Bug détecté sur l'écran des profils"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["note_id"] > 0
        assert data["note"]["category"] == "bug_report"
        assert "Erreur 500" in data["note"]["content"]
        assert "bug" in data["note"]["tags"]
        assert "analysé votre capture" in data["spoken_response"].lower()

        # Vérification persistance en base SQLite
        saved_note = db.get_note(data["note_id"])
        assert saved_note is not None
        assert saved_note["category"] == "bug_report"

        # Vérification trace dans conversation_logs
        logs = db.get_conversation_logs(limit=1)
        assert logs["total"] > 0
        last_log = logs["items"][0]
        assert "image" in last_log["intent"].lower() or "second_brain" in last_log["intent"].lower()


def test_api_upload_image_vacation_dynamic_category():
    """Vérifie qu'un screenshot d'hôtel/destination est auto-classé en catégorie 'voyage'."""
    client = TestClient(app)
    db = get_database_manager()
    db.init_db()

    vacation_analysis = SecondBrainImageAnalysisResult(
        category="voyage",
        title="Hôtel vue mer en Corse - Santa Giulia",
        summary="Capture d'une annonce Booking.com pour un hôtel les pieds dans l'eau à Santa Giulia pour l'été prochain.",
        tags=["vacances", "corse", "hotel", "été"],
        suggested_action="Consulter les disponibilités pour juillet.",
    )

    fake_jpeg = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIFfakejpegdata")

    with patch("app.routers.second_brain.analyze_image_for_second_brain") as mock_analyze:
        mock_analyze.return_value = vacation_analysis

        response = client.post(
            "/api/v1/second-brain/notes/image",
            files={"image": ("hotel.jpg", fake_jpeg, "image/jpeg")},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["note"]["category"] == "voyage"
        assert "Santa Giulia" in data["note"]["content"]


def test_api_upload_image_rejects_unsupported_mime_type():
    """Vérifie que les fichiers non-images sont refusés avec une 400 claire."""
    client = TestClient(app)
    fake_txt = io.BytesIO(b"ceci est un simple fichier texte")

    response = client.post(
        "/api/v1/second-brain/notes/image",
        files={"image": ("document.txt", fake_txt, "text/plain")},
    )

    assert response.status_code == 400
    assert "image/png" in response.json()["detail"].lower()


def test_api_upload_image_category_override(mock_vision_gemini_analysis):
    """Vérifie que category_override force la catégorie si spécifié."""
    client = TestClient(app)
    fake_file = io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRfakeimagedata")

    with patch("app.routers.second_brain.analyze_image_for_second_brain") as mock_analyze:
        mock_analyze.return_value = mock_vision_gemini_analysis

        response = client.post(
            "/api/v1/second-brain/notes/image",
            files={"image": ("screenshot.png", fake_file, "image/png")},
            data={"category_override": "super_projet"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["note"]["category"] == "super_projet"
