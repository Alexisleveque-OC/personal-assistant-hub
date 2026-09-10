"""Module de validation de structure et détection de dérive (Schema Drift) du Google Sheet."""
from datetime import datetime
import unicodedata
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.connectors.sheets.models import SheetSchemaSnapshot


class SheetSchemaError(Exception):
    """Erreur de base pour toute anomalie de structure du Google Sheet."""
    pass


class SheetSchemaWorksheetNotFoundError(SheetSchemaError):
    """Levée lorsqu'un onglet obligatoire est introuvable dans le classeur."""

    def __init__(self, missing_sheet: str, available_sheets: List[str]):
        self.missing_sheet = missing_sheet
        self.available_sheets = available_sheets
        super().__init__(
            f"Onglet obligatoire introuvable dans le Google Sheet : '{missing_sheet}'. "
            f"Onglets actuellement disponibles : {available_sheets}."
        )


class SheetSchemaHeaderDriftError(SheetSchemaError):
    """Levée lorsqu'une dérive de colonnes ou d'en-têtes est détectée dans un onglet."""

    def __init__(
        self,
        sheet_name: str,
        missing_columns: List[str],
        actual_columns: List[str],
        expected_columns: List[str],
    ):
        self.sheet_name = sheet_name
        self.missing_columns = missing_columns
        self.actual_columns = actual_columns
        self.expected_columns = expected_columns
        super().__init__(
            f"Dérive de structure détectée dans l'onglet '{sheet_name}'. "
            f"Colonnes obligatoires manquantes : {missing_columns}. "
            f"Colonnes trouvées : {actual_columns}. "
            f"Colonnes attendues : {expected_columns}."
        )


class ValidationReport(BaseModel):
    """Rapport d'audit de conformité du schéma du Google Sheet."""
    is_valid: bool = True
    checked_worksheets: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


def normalize_header(name: str) -> str:
    """Normalise une chaîne pour comparaison robuste (sans accents, minuscules, sans espaces superflus)."""
    if not name:
        return ""
    # Suppression des accents et normalisation unicode
    nfkd = unicodedata.normalize("NFKD", name.strip())
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    return no_accents.lower()


class SheetSchemaValidator:
    """Valide la conformité structurelle d'un Google Sheet partagé et détecte les dérives."""

    def __init__(self, snapshot: Optional[SheetSchemaSnapshot] = None):
        self.snapshot = snapshot or SheetSchemaSnapshot()

    def get_expected_worksheets(self, year: Optional[int] = None) -> List[str]:
        """Retourne la liste complète des onglets requis pour une année donnée."""
        target_year = year or datetime.now().year
        annual_sheet = f"repas {target_year}"
        # On place l'onglet annuel en premier, suivi des onglets fixes
        return [annual_sheet] + list(self.snapshot.required_worksheets)

    def get_expected_headers_for_sheet(self, sheet_title: str) -> Optional[List[str]]:
        """Retourne la liste des en-têtes requis selon l'onglet."""
        lower_title = sheet_title.strip().lower()

        if lower_title.startswith("repas "):
            return self.snapshot.planning_headers
        if lower_title in ("recettes", "recette festive"):
            return self.snapshot.recipes_headers
        if lower_title == "rayons":
            return self.snapshot.rayons_headers
        if lower_title == "hors_repas":
            return self.snapshot.hors_repas_headers
        if lower_title == "ingredients_rayons":
            return self.snapshot.ingredients_rayons_headers
        if lower_title == "cette semaine":
            # Cette semaine a 'Midi' et 'Soir' en ligne 1
            return ["Midi", "Soir"]

        return None

    def validate_worksheet_existence(
        self,
        available_sheet_titles: List[str],
        year: Optional[int] = None,
    ) -> List[str]:
        """Vérifie la présence de tous les onglets obligatoires."""
        expected_sheets = self.get_expected_worksheets(year=year)
        available_set = {s.strip() for s in available_sheet_titles}
        missing_sheets = [s for s in expected_sheets if s not in available_set]
        return missing_sheets

    def validate_sheet_headers(
        self,
        sheet_title: str,
        actual_headers: List[str],
        expected_headers: List[str],
    ) -> List[str]:
        """Vérifie que tous les en-têtes obligatoires sont présents parmi les en-têtes réels."""
        normalized_actual = {normalize_header(h) for h in actual_headers if h}
        missing_cols = [
            col for col in expected_headers if normalize_header(col) not in normalized_actual
        ]
        return missing_cols

    def validate_all(
        self,
        spreadsheet: Any,
        year: Optional[int] = None,
        strict: bool = True,
    ) -> ValidationReport:
        """Exécute la validation complète du tableur.

        Args:
            spreadsheet: Instance gspread.Spreadsheet ou mock équivalent.
            year: Année cible pour le planning (défaut: année courante).
            strict: Si True, lève immédiatement une exception explicite dès la première erreur.

        Returns:
            ValidationReport détaillant les résultats de la validation.
        """
        report = ValidationReport()
        target_year = year or datetime.now().year

        # 1. Vérification des onglets existants
        all_worksheets = spreadsheet.worksheets()
        available_titles = [ws.title for ws in all_worksheets]
        ws_by_title: Dict[str, Any] = {ws.title.strip(): ws for ws in all_worksheets}

        missing_sheets = self.validate_worksheet_existence(available_titles, year=target_year)
        if missing_sheets:
            report.is_valid = False
            for missing in missing_sheets:
                err_msg = f"Onglet obligatoire manquant : '{missing}'"
                report.errors.append(err_msg)
                if strict:
                    raise SheetSchemaWorksheetNotFoundError(
                        missing_sheet=missing,
                        available_sheets=available_titles,
                    )

        # 2. Vérification des en-têtes pour chaque onglet présent
        expected_sheets = self.get_expected_worksheets(year=target_year)
        for sheet_name in expected_sheets:
            if sheet_name not in ws_by_title:
                continue

            report.checked_worksheets.append(sheet_name)
            ws = ws_by_title[sheet_name]
            expected_headers = self.get_expected_headers_for_sheet(sheet_name)

            if not expected_headers:
                continue

            # Lecture de la première ligne
            try:
                actual_headers = ws.row_values(1)
            except Exception as e:
                err_msg = f"Impossible de lire la première ligne de l'onglet '{sheet_name}': {e}"
                report.is_valid = False
                report.errors.append(err_msg)
                if strict:
                    raise SheetSchemaError(err_msg) from e
                continue

            missing_cols = self.validate_sheet_headers(
                sheet_title=sheet_name,
                actual_headers=actual_headers,
                expected_headers=expected_headers,
            )

            if missing_cols:
                report.is_valid = False
                err_msg = (
                    f"Onglet '{sheet_name}' : colonnes manquantes {missing_cols}. "
                    f"Trouvées : {actual_headers}."
                )
                report.errors.append(err_msg)
                if strict:
                    raise SheetSchemaHeaderDriftError(
                        sheet_name=sheet_name,
                        missing_columns=missing_cols,
                        actual_columns=actual_headers,
                        expected_columns=expected_headers,
                    )

        return report
