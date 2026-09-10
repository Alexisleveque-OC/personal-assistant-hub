"""Tests unitaires et d'intégration pour la détection de dérive (Schema Drift) du Google Sheet."""
import os
from unittest.mock import MagicMock
import pytest
from dotenv import load_dotenv

from app.connectors.sheets.schema_validator import (
    SheetSchemaValidator,
    SheetSchemaWorksheetNotFoundError,
    SheetSchemaHeaderDriftError,
    SheetSchemaError,
)

load_dotenv()

LIVE_CREDS_PATH = os.path.join("credentials", "service_account.json")
LIVE_SHEET_ID = os.getenv("SPREADSHEET_MEALS_SHOPPING_ID")
HAS_LIVE_ENV = bool(
    os.path.exists(LIVE_CREDS_PATH)
    and LIVE_SHEET_ID
    and not LIVE_SHEET_ID.startswith("votre_")
)


def create_mock_worksheet(title: str, headers: list[str]) -> MagicMock:
    """Crée un mock de feuille avec titre et première ligne d'en-têtes."""
    ws = MagicMock()
    ws.title = title
    ws.row_values.return_value = headers
    return ws


def create_mock_spreadsheet_conforming(year: int = 2026) -> MagicMock:
    """Crée un mock de classeur 100% conforme au schéma attendu."""
    worksheets = [
        create_mock_worksheet(f"repas {year}", ["Date", "Jour", "Midi", "Soir", "Notes / Magasin"]),
        create_mock_worksheet("Cette semaine", ["", "", "Midi", "", "Soir"]),
        create_mock_worksheet("Recettes", ["Plat", "Catégorie", "Catégorie 2", "Complet", "Ingrédient"]),
        create_mock_worksheet("Recette festive", ["Plat", "Catégorie", "Catégorie 2", "Complet", "Ingrédient"]),
        create_mock_worksheet("Courses festives", ["Fruits", "", "Légumes", "", "Plat préparé"]),
        create_mock_worksheet("Rayons", ["Rayons", "Ordre"]),
        create_mock_worksheet("Hors_Repas", ["Nom", "pré-cocher?", "rayon"]),
        create_mock_worksheet("Ingredients_Rayons", ["Ingrédient", "Rayon"]),
    ]
    sh = MagicMock()
    sh.worksheets.return_value = worksheets
    return sh


def test_schema_validator_conforming_sheet_passes():
    """Vérifie qu'un classeur conforme retourne un rapport valide sans erreur."""
    sh = create_mock_spreadsheet_conforming(year=2026)
    validator = SheetSchemaValidator()

    report = validator.validate_all(sh, year=2026, strict=True)

    assert report.is_valid is True
    assert len(report.errors) == 0
    assert f"repas 2026" in report.checked_worksheets
    assert "Recettes" in report.checked_worksheets
    assert "Recette festive" in report.checked_worksheets
    assert "Courses festives" in report.checked_worksheets
    assert "Ingredients_Rayons" in report.checked_worksheets


def test_schema_validator_missing_annual_worksheet_raises_explicit_error():
    """Vérifie qu'un onglet annuel manquant lève une SheetSchemaWorksheetNotFoundError explicite."""
    sh = MagicMock()
    # Classeur ne contenant que repas 2025, alors qu'on demande 2027
    sh.worksheets.return_value = [
        create_mock_worksheet("repas 2025", ["Date", "Jour", "Midi", "Soir"]),
        create_mock_worksheet("Recettes", ["Plat", "Catégorie", "Catégorie 2", "Complet", "Ingrédient"]),
    ]
    validator = SheetSchemaValidator()

    with pytest.raises(SheetSchemaWorksheetNotFoundError) as exc_info:
        validator.validate_all(sh, year=2027, strict=True)

    assert "repas 2027" in str(exc_info.value)
    assert exc_info.value.missing_sheet == "repas 2027"
    assert "repas 2025" in exc_info.value.available_sheets


def test_schema_validator_missing_static_worksheet_raises_explicit_error():
    """Vérifie qu'un onglet critique manquant (ex: Recettes) lève une exception claire."""
    sh = MagicMock()
    # Tous les onglets sauf Recettes
    sh.worksheets.return_value = [
        create_mock_worksheet("repas 2026", ["Date", "Jour", "Midi", "Soir"]),
        create_mock_worksheet("Cette semaine", ["", "", "Midi", "", "Soir"]),
        create_mock_worksheet("Recette festive", ["Plat", "Catégorie", "Catégorie 2", "Complet", "Ingrédient"]),
        create_mock_worksheet("Courses festives", ["Fruits"]),
        create_mock_worksheet("Rayons", ["Rayons", "Ordre"]),
        create_mock_worksheet("Hors_Repas", ["Nom", "pré-cocher?", "rayon"]),
        create_mock_worksheet("Ingredients_Rayons", ["Ingrédient", "Rayon"]),
    ]
    validator = SheetSchemaValidator()

    with pytest.raises(SheetSchemaWorksheetNotFoundError) as exc_info:
        validator.validate_all(sh, year=2026, strict=True)

    assert "Recettes" in str(exc_info.value)
    assert exc_info.value.missing_sheet == "Recettes"


def test_schema_validator_header_drift_in_planning_raises_explicit_error():
    """Vérifie qu'une colonne obligatoire manquante dans repas 2026 lève SheetSchemaHeaderDriftError."""
    sh = MagicMock()
    sh.worksheets.return_value = [
        # Colonnes 'Midi' et 'Soir' absentes
        create_mock_worksheet("repas 2026", ["Date", "Jour", "Notes / Magasin"]),
        create_mock_worksheet("Cette semaine", ["", "", "Midi", "", "Soir"]),
        create_mock_worksheet("Recettes", ["Plat", "Catégorie", "Catégorie 2", "Complet", "Ingrédient"]),
        create_mock_worksheet("Recette festive", ["Plat", "Catégorie", "Catégorie 2", "Complet", "Ingrédient"]),
        create_mock_worksheet("Courses festives", ["Fruits"]),
        create_mock_worksheet("Rayons", ["Rayons", "Ordre"]),
        create_mock_worksheet("Hors_Repas", ["Nom", "pré-cocher?", "rayon"]),
        create_mock_worksheet("Ingredients_Rayons", ["Ingrédient", "Rayon"]),
    ]
    validator = SheetSchemaValidator()

    with pytest.raises(SheetSchemaHeaderDriftError) as exc_info:
        validator.validate_all(sh, year=2026, strict=True)

    err = exc_info.value
    assert err.sheet_name == "repas 2026"
    assert "Midi" in err.missing_columns
    assert "Soir" in err.missing_columns
    assert "Date" in err.actual_columns


def test_schema_validator_header_drift_in_recettes_raises_explicit_error():
    """Vérifie qu'un renommage de colonne critique dans Recettes est détecté immédiatement."""
    sh = MagicMock()
    sh.worksheets.return_value = [
        create_mock_worksheet("repas 2026", ["Date", "Jour", "Midi", "Soir", "Notes / Magasin"]),
        create_mock_worksheet("Cette semaine", ["", "", "Midi", "", "Soir"]),
        # Colonne 'Plat' renommée par erreur en 'Nom_Du_Repas'
        create_mock_worksheet("Recettes", ["Nom_Du_Repas", "Catégorie", "Catégorie 2", "Complet", "Ingrédient"]),
        create_mock_worksheet("Recette festive", ["Plat", "Catégorie", "Catégorie 2", "Complet", "Ingrédient"]),
        create_mock_worksheet("Courses festives", ["Fruits"]),
        create_mock_worksheet("Rayons", ["Rayons", "Ordre"]),
        create_mock_worksheet("Hors_Repas", ["Nom", "pré-cocher?", "rayon"]),
        create_mock_worksheet("Ingredients_Rayons", ["Ingrédient", "Rayon"]),
    ]
    validator = SheetSchemaValidator()

    with pytest.raises(SheetSchemaHeaderDriftError) as exc_info:
        validator.validate_all(sh, year=2026, strict=True)

    err = exc_info.value
    assert err.sheet_name == "Recettes"
    assert "Plat" in err.missing_columns


def test_schema_validator_non_strict_mode_aggregates_multiple_errors():
    """Vérifie qu'en mode strict=False, le validateur agrège toutes les dérives sans lever d'exception."""
    sh = MagicMock()
    # Plusieurs anomalies : onglet Recette festive manquant ET colonne Hors_Repas erronée
    sh.worksheets.return_value = [
        create_mock_worksheet("repas 2026", ["Date", "Jour", "Midi", "Soir"]),
        create_mock_worksheet("Cette semaine", ["", "", "Midi", "", "Soir"]),
        create_mock_worksheet("Recettes", ["Plat", "Catégorie", "Catégorie 2", "Complet", "Ingrédient"]),
        create_mock_worksheet("Courses festives", ["Fruits"]),
        create_mock_worksheet("Rayons", ["Rayons", "Ordre"]),
        create_mock_worksheet("Hors_Repas", ["Nom", "pré-cocher?"]),  # 'rayon' manquant
        create_mock_worksheet("Ingredients_Rayons", ["Ingrédient", "Rayon"]),
        # 'Recette festive' complètement absent
    ]
    validator = SheetSchemaValidator()

    report = validator.validate_all(sh, year=2026, strict=False)

    assert report.is_valid is False
    assert len(report.errors) >= 2
    assert any("Recette festive" in err for err in report.errors)
    assert any("Hors_Repas" in err for err in report.errors)


@pytest.mark.skipif(not HAS_LIVE_ENV, reason="Identifiants GCP ou SPREADSHEET_ID absents")
def test_live_google_sheet_schema_conformity():
    """Test d'intégration réel : valide que le Google Sheet réel de production est 100% conforme."""
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_file(
        LIVE_CREDS_PATH,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    client = gspread.authorize(creds)
    sh = client.open_by_key(LIVE_SHEET_ID)

    validator = SheetSchemaValidator()
    report = validator.validate_all(sh, year=2026, strict=True)

    assert report.is_valid is True
    assert len(report.errors) == 0
    # Vérifie que les onglets indispensables ont tous été audités
    for mandatory in ["repas 2026", "Cette semaine", "Recettes", "Recette festive", "Courses festives", "Rayons", "Hors_Repas", "Ingredients_Rayons"]:
        assert mandatory in report.checked_worksheets
