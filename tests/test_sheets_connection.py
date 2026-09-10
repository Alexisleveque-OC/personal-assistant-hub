from datetime import datetime
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch

from app.config import settings


class PlanningWorksheetNotFoundError(Exception):
    """Exception explicite levée lorsqu'un onglet de planning annuel est introuvable."""
    pass


def resolve_meals_worksheet_name(available_worksheets: list[str], year: int | None = None) -> str:
    """Résout le nom de l'onglet annuel (ex: 'repas 2026', 'repas 2027') ou lève une erreur explicite."""
    target_year = year or datetime.now().year
    expected_name = f"repas {target_year}"
    if expected_name not in available_worksheets:
        raise PlanningWorksheetNotFoundError(
            f"L'onglet de planning annuel '{expected_name}' est introuvable dans le Google Sheet. "
            f"Veuillez créer l'onglet '{expected_name}' dans votre tableur pour l'année {target_year}. "
            f"Onglets actuellement disponibles : {available_worksheets}"
        )
    return expected_name


def test_dynamic_year_sheet_name_resolution():
    """Vérifie la résolution dynamique réussie quand l'onglet de l'année existe."""
    existing_sheets = ["Cette semaine", "Recettes", "repas 2025", "repas 2026", "repas 2027"]
    assert resolve_meals_worksheet_name(existing_sheets, 2026) == "repas 2026"
    assert resolve_meals_worksheet_name(existing_sheets, 2027) == "repas 2027"

    # Avec l'année en cours par défaut
    current_year = datetime.now().year
    assert resolve_meals_worksheet_name(existing_sheets) == f"repas {current_year}"


def test_explicit_error_when_future_year_sheet_is_missing():
    """Vérifie qu'une erreur explicite est levée si on demande 2027 et que l'onglet n'a pas encore été créé."""
    # Simulation : seules les années 2025 et 2026 existent dans le tableur
    existing_sheets = ["Cette semaine", "repas 2026", "Recettes", "repas 2025"]

    with pytest.raises(PlanningWorksheetNotFoundError) as exc_info:
        resolve_meals_worksheet_name(existing_sheets, year=2027)

    # Vérification que le message est ultra-explicite pour l'utilisateur et pour l'agent
    error_msg = str(exc_info.value)
    assert "repas 2027" in error_msg
    assert "Veuillez créer l'onglet 'repas 2027'" in error_msg
    assert "Onglets actuellement disponibles" in error_msg


def test_sheets_connection_mocked():
    """Test unitaire du mécanisme de connexion (mocké pour la CI/mode hors-ligne) avec résolution dynamique."""
    current_year = datetime.now().year
    expected_sheet = f"repas {current_year}"

    with patch("gspread.service_account") as mock_sa:
        mock_gc = MagicMock()
        mock_sheet = MagicMock()
        mock_sheet.title = "Semaine de repas 2025"
        mock_sheet.worksheets.return_value = [
            MagicMock(title="Cette semaine"),
            MagicMock(title=expected_sheet),
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
        resolved = resolve_meals_worksheet_name(titles)
        assert resolved == expected_sheet
        assert "Recettes" in titles


@pytest.mark.skipif(
    not Path(settings.google_service_account_file).exists()
    or not settings.spreadsheet_meals_shopping_id,
    reason="Identifiants Google Sheets réels non disponibles (ex: environnement CI)",
)
def test_live_sheets_connection():
    """Test d'intégration en conditions réelles avec validation de l'onglet de l'année en cours."""
    import gspread

    gc = gspread.service_account(filename=settings.google_service_account_file)
    sh = gc.open_by_key(settings.spreadsheet_meals_shopping_id)

    assert sh.title is not None
    worksheet_names = [ws.title for ws in sh.worksheets()]
    
    # Résolution sécurisée : lève l'erreur explicite PlanningWorksheetNotFoundError si l'année en cours est absente
    resolved_sheet = resolve_meals_worksheet_name(worksheet_names)
    assert resolved_sheet == f"repas {datetime.now().year}"
    assert "Recettes" in worksheet_names
    assert "Cette semaine" in worksheet_names
