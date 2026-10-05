"""Tests de conformité et de détection de dérive (Schema Drift) pour le Google Sheet Sport."""
import json
import pytest
import gspread

from app.config import settings
from app.connectors.sheets.sport_schema import (
    SportSchemaValidator,
    SportWorksheetNotFoundError,
    SportHeaderDriftError,
    CANONICAL_SEANCES_COLUMNS,
    EXPECTED_SYNTHESE_HEBDO_HEADERS,
)


def test_sport_schema_validator_conforming_sheet_passes():
    """Valide que le schéma complet (Séance + Synthese_Hebdo) est reconnu conforme."""
    available_worksheets = ["Séance", "Synthese_Hebdo"]
    headers_by_worksheet = {
        "Séance": CANONICAL_SEANCES_COLUMNS,
        "Synthese_Hebdo": EXPECTED_SYNTHESE_HEBDO_HEADERS,
    }

    validator = SportSchemaValidator(strict=True)
    result = validator.validate(available_worksheets, headers_by_worksheet)

    assert result.is_valid is True
    assert result.resolved_seances_sheet == "Séance"
    assert result.resolved_synthese_sheet == "Synthese_Hebdo"
    assert len(result.errors) == 0


def test_sport_schema_validator_missing_seances_worksheet_raises_error():
    """Lève une exception explicite si l'onglet Séance est manquant."""
    available_worksheets = ["Synthese_Hebdo"]
    headers_by_worksheet = {"Synthese_Hebdo": EXPECTED_SYNTHESE_HEBDO_HEADERS}

    validator = SportSchemaValidator(strict=True)
    with pytest.raises(SportWorksheetNotFoundError) as exc_info:
        validator.validate(available_worksheets, headers_by_worksheet)

    assert "Séance" in str(exc_info.value)


def test_sport_schema_validator_missing_synthese_worksheet_raises_error():
    """Lève une exception explicite si l'onglet Synthese_Hebdo est manquant."""
    available_worksheets = ["Séance"]
    headers_by_worksheet = {"Séance": CANONICAL_SEANCES_COLUMNS}

    validator = SportSchemaValidator(strict=True)
    with pytest.raises(SportWorksheetNotFoundError) as exc_info:
        validator.validate(available_worksheets, headers_by_worksheet)

    assert "Synthese_Hebdo" in str(exc_info.value)


def test_sport_schema_validator_header_drift_raises_error():
    """Lève une exception explicite lorsqu'une colonne obligatoire a été altérée."""
    available_worksheets = ["Séance", "Synthese_Hebdo"]
    drifted_seances = list(CANONICAL_SEANCES_COLUMNS)
    drifted_seances[4] = "Dist_Kilometres"  # Erreur de nommage !

    headers_by_worksheet = {
        "Séance": drifted_seances,
        "Synthese_Hebdo": EXPECTED_SYNTHESE_HEBDO_HEADERS,
    }

    validator = SportSchemaValidator(strict=True)
    with pytest.raises(SportHeaderDriftError) as exc_info:
        validator.validate(available_worksheets, headers_by_worksheet)

    assert "Distance" in str(exc_info.value)


@pytest.mark.skipif(not settings.spreadsheet_sport_id, reason="SPREADSHEET_SPORT_ID non configuré")
def test_live_google_sheet_sport_conformity():
    """Vérifie la conformité en direct du Google Sheet Sport réel d'Alexis."""
    if settings.google_service_account_info:
        gc = gspread.service_account_from_dict(json.loads(settings.google_service_account_info))
    else:
        gc = gspread.service_account(filename=settings.google_service_account_file)

    sh = gc.open_by_key(settings.spreadsheet_sport_id)
    available_sheets = [ws.title for ws in sh.worksheets()]
    headers_by_sheet = {ws.title: ws.row_values(1) for ws in sh.worksheets()}

    validator = SportSchemaValidator(strict=True)
    report = validator.validate(available_sheets, headers_by_sheet)

    assert report.is_valid is True
    assert report.resolved_seances_sheet is not None
    assert report.resolved_synthese_sheet is not None
