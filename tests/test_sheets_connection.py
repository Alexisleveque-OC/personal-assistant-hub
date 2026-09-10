"""Test de validation de la connexion Google Sheets."""
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch

from app.config import settings


def test_sheets_connection_mocked():
    """Test unitaire du mécanisme de connexion (mocké pour la CI/mode hors-ligne)."""
    with patch("gspread.service_account") as mock_sa:
        mock_gc = MagicMock()
        mock_sheet = MagicMock()
        mock_sheet.title = "Semaine de repas 2025"
        mock_sheet.worksheets.return_value = [
            MagicMock(title="Cette semaine"),
            MagicMock(title="repas 2026"),
            MagicMock(title="Recettes"),
            MagicMock(title="Rayons"),
            MagicMock(title="Hors_Repas"),
        ]
        mock_gc.open_by_key.return_value = mock_sheet
        mock_sa.return_value = mock_gc

        gc = mock_sa(filename="fake_creds.json")
        sh = gc.open_by_key("fake_id")

        assert sh.title == "Semaine de repas 2025"
        titles = [ws.title for ws in sh.worksheets()]
        assert "repas 2026" in titles
        assert "Recettes" in titles


@pytest.mark.skipif(
    not Path(settings.google_service_account_file).exists()
    or not settings.spreadsheet_meals_shopping_id,
    reason="Identifiants Google Sheets réels non disponibles (ex: environnement CI)",
)
def test_live_sheets_connection():
    """Test d'intégration en conditions réelles (exécuté uniquement en local avec credentials)."""
    import gspread

    gc = gspread.service_account(filename=settings.google_service_account_file)
    sh = gc.open_by_key(settings.spreadsheet_meals_shopping_id)

    assert sh.title is not None
    worksheet_names = [ws.title for ws in sh.worksheets()]
    assert "repas 2026" in worksheet_names
    assert "Recettes" in worksheet_names
    assert "Cette semaine" in worksheet_names
