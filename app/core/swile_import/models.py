"""Contrats de l'import Swile : capture lue par Gemini Vision (montants signés tels qu'affichés)."""
from datetime import date as dt_date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class SwileCaptureLine(BaseModel):
    """Ligne lue : `montant` négatif pour un paiement, positif pour un crédit de titres-resto."""
    marchand: str
    date_texte: str = Field(description="Date telle qu'affichée (« Hier, 17:35 », « mercredi 25 nov. 2026, 17:35 »).")
    montant: float


class SwileCapture(BaseModel):
    is_swile: bool
    solde: Optional[float] = Field(None, description="Solde « Titres-resto » de l'accueil, absent ailleurs.")
    lignes: List[SwileCaptureLine] = Field(default_factory=list)
    message: Optional[str] = None


LineType = Literal["depense", "credit"]


class SwileReviewLine(BaseModel):
    """Ligne proposée à la relecture : montant positif ; `doublon` (« déjà saisie le JJ/MM (catégorie) ? ») → décochée."""
    type: LineType
    date: dt_date
    montant: float = Field(gt=0)
    marchand: str
    categorie: Optional[str] = Field(None, description="Tri auto, sinon nom appris ; « Ticket resto » pour un crédit.")
    doublon: Optional[str] = None
    cochee: bool


class SwileBalanceView(BaseModel):
    nouveau: float
    actuel: Optional[float] = Field(None, description="Valeur de la case « Reste Swile » du mois ; None si vide.")
    mois: str


class SwileReview(BaseModel):
    lignes: List[SwileReviewLine]
    solde: Optional[SwileBalanceView] = None
    avertissements: List[str] = Field(default_factory=list, description="Captures et lignes ignorées, avec la raison.")


class SwileImportLine(BaseModel):
    """Ligne cochée à la relecture ; `categorie` = nom choisi dans la liste (type de revenu pour un crédit)."""
    type: LineType
    date: dt_date
    montant: float = Field(gt=0)
    marchand: str
    categorie: str = Field(min_length=1)

    @field_validator("marchand")
    @classmethod
    def _merchant(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Le marchand est vide.")
        return value.strip()


class SwileImportForm(BaseModel):
    """Import relu ; `type` (constant) sert au libellé de « Dernières actions »."""
    type: Literal["swile"] = "swile"
    lignes: List[SwileImportLine] = Field(default_factory=list)
    solde: Optional[float] = Field(None, ge=0, description="Solde à écrire dans « Reste Swile » ; None = ne pas l'écrire.")
    session_id: str = Field(min_length=1, description="Session de l'appareil : lui seul peut annuler l'import.")

    @model_validator(mode="after")
    def _something_to_import(self) -> "SwileImportForm":
        if not self.lignes and self.solde is None:
            raise ValueError("Rien à importer : aucune ligne cochée et pas de solde.")
        return self
