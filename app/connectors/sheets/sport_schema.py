"""Module de validation de structure et détection de dérive (Schema Drift) du Google Sheet Sport Running."""
import unicodedata
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

# Noms d'onglets canoniques et alias acceptés
SEANCES_SHEET_ALIASES = ["seance", "seances", "seance running", "running"]
SYNTHESE_SHEET_ALIASES = ["synthese_hebdo", "synthese hebdo", "synthese", "dashboard"]

# Ordre logique officiel des colonnes de l'onglet Séance
CANONICAL_SEANCES_COLUMNS = [
    "Date",
    "Semaine",
    "Statut",
    "Type de séance",
    "Distance (km)",
    "Dénivelé D+ (m)",
    "Km-Effort",
    "Temps",
    "Vitesse (km/h)",
    "Allure (min/km)",
    "ressenti dur/10",
    "Charge RPE",
    "FC Moy (bpm)",
    "FC Max (bpm)",
    "Météo difficile/10",
    "Programme",
    "Remarques",
    "ID Strava",
]

EXPECTED_SYNTHESE_HEBDO_HEADERS = [
    "Semaine",
    "Année",
    "Nb Séances",
    "Km Totaux",
    "D+ Total",
    "Km-Effort Total",
    "Durée Totale",
    "Allure Moyenne",
    "Évolution vs S-1 (%)",
    "Alerte Sécurité",
    "Plafond Conseillé S+1",
]

SYNTHESE_HEBDO_EXTENDED_HEADERS = [
    "Semaine",
    "Année",
    "Nb Séances",
    "Km Totaux",
    "D+ Total",
    "Km-Effort Total",
    "Durée Totale",
    "Allure Moyenne",
    "Vitesse Moyenne",
    "Charge RPE",
    "Évol Volume (%)",
    "Évol Vitesse (%)",
    "Évol RPE (%)",
    "Progression Générale (%)",
    "Alerte Sécurité",
    "Plafond Conseillé S+1",
]


class SportSchemaError(Exception):
    """Erreur de base pour toute anomalie de structure du Google Sheet Sport."""
    pass


class SportWorksheetNotFoundError(SportSchemaError):
    """Levée lorsqu'un onglet obligatoire du module sport est introuvable."""

    def __init__(self, missing_sheet: str, available_sheets: List[str]):
        self.missing_sheet = missing_sheet
        self.available_sheets = available_sheets
        super().__init__(
            f"Onglet obligatoire introuvable dans le Google Sheet Sport : '{missing_sheet}'. "
            f"Onglets actuellement disponibles : {available_sheets}. "
            f"Veuillez créer l'onglet '{missing_sheet}' dans votre classeur."
        )


class SportHeaderDriftError(SportSchemaError):
    """Levée lorsqu'une dérive de colonnes ou d'en-têtes est détectée dans un onglet sport."""

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
            f"Dérive de structure détectée dans l'onglet sport '{sheet_name}'. "
            f"Colonnes obligatoires manquantes : {missing_columns}. "
            f"Colonnes trouvées : {actual_columns}. "
            f"Colonnes attendues : {expected_columns}."
        )


class SportValidationReport(BaseModel):
    """Rapport d'audit de conformité du schéma du Google Sheet Sport."""
    is_valid: bool = True
    checked_worksheets: List[str] = Field(default_factory=list)
    resolved_seances_sheet: Optional[str] = None
    resolved_synthese_sheet: Optional[str] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


def normalize_name(name: str) -> str:
    """Normalise un nom ou en-tête pour comparaison robuste (sans accents, minuscules, espaces simples)."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", name).encode("ASCII", "ignore").decode("utf-8")
    return " ".join(text.lower().strip().replace("_", " ").replace("-", " ").split())


def resolve_worksheet(available_worksheets: List[str], aliases: List[str]) -> Optional[str]:
    """Trouve un onglet parmi les disponibles correspondant à l'un des alias normalisés."""
    normalized_aliases = [normalize_name(a) for a in aliases]
    for ws in available_worksheets:
        if normalize_name(ws) in normalized_aliases:
            return ws
    return None


class SportSchemaValidator:
    """Validateur de conformité structurelle pour le classeur Google Sheets Sport."""

    def __init__(self, strict: bool = False):
        self.strict = strict

    def validate(
        self,
        available_worksheets: List[str],
        headers_by_worksheet: Dict[str, List[str]],
    ) -> SportValidationReport:
        report = SportValidationReport()

        # 1. Résolution de l'onglet Séance
        seances_title = resolve_worksheet(available_worksheets, SEANCES_SHEET_ALIASES)
        if not seances_title:
            msg = "Onglet 'Séance' ou 'Seances' introuvable dans le Google Sheet Sport."
            report.errors.append(msg)
            report.is_valid = False
            if self.strict:
                raise SportWorksheetNotFoundError("Séance", available_worksheets)
        else:
            report.resolved_seances_sheet = seances_title
            report.checked_worksheets.append(seances_title)

            actual_headers = headers_by_worksheet.get(seances_title, [])
            actual_norm = [normalize_name(h) for h in actual_headers]

            missing_cols = []
            has_programme = any(normalize_name(a) in actual_norm for a in ["Programme", "Detail Seance", "Exercices", "Contenu"])
            has_remarques = any(normalize_name(a) in actual_norm for a in ["Remarques", "Remarque", "Note", "Notes"])

            for col in CANONICAL_SEANCES_COLUMNS:
                if col == "Programme":
                    if not has_programme and not has_remarques:
                        missing_cols.append("Programme")
                elif col == "Remarques":
                    if not has_remarques:
                        missing_cols.append("Remarques")
                else:
                    if normalize_name(col) not in actual_norm:
                        missing_cols.append(col)

            if missing_cols:
                msg = f"Colonnes obligatoires manquantes dans '{seances_title}' : {missing_cols}"
                report.errors.append(msg)
                report.is_valid = False
                if self.strict:
                    raise SportHeaderDriftError(
                        sheet_name=seances_title,
                        missing_columns=missing_cols,
                        actual_columns=actual_headers,
                        expected_columns=CANONICAL_SEANCES_COLUMNS,
                    )

        # 2. Résolution de l'onglet Synthese_Hebdo
        synthese_title = resolve_worksheet(available_worksheets, SYNTHESE_SHEET_ALIASES)
        if not synthese_title:
            msg = "Onglet 'Synthese_Hebdo' introuvable dans le Google Sheet Sport."
            report.errors.append(msg)
            report.is_valid = False
            if self.strict:
                raise SportWorksheetNotFoundError("Synthese_Hebdo", available_worksheets)
        else:
            report.resolved_synthese_sheet = synthese_title
            report.checked_worksheets.append(synthese_title)

            actual_headers_syn = headers_by_worksheet.get(synthese_title, [])
            actual_norm_syn = [normalize_name(h) for h in actual_headers_syn]

            is_extended = any("progression generale" in h or "charge rpe" in h for h in actual_norm_syn)
            target_expected = SYNTHESE_HEBDO_EXTENDED_HEADERS if is_extended else EXPECTED_SYNTHESE_HEBDO_HEADERS

            missing_cols_syn = []
            for col in target_expected:
                if normalize_name(col) not in actual_norm_syn:
                    missing_cols_syn.append(col)

            if missing_cols_syn:
                msg = f"Colonnes manquantes dans '{synthese_title}' : {missing_cols_syn}"
                report.errors.append(msg)
                report.is_valid = False
                if self.strict:
                    raise SportHeaderDriftError(
                        sheet_name=synthese_title,
                        missing_columns=missing_cols_syn,
                        actual_columns=actual_headers_syn,
                        expected_columns=target_expected,
                    )

        return report
