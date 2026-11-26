"""Contrats des formulaires de l'écran Budget (Phase 10, étapes 7b et 7c) : Dépense / Revenu, Échéancier, Dépense
multiple. `type` (constant) sert au libellé de « Dernières actions » ; `session_id` désigne l'appareil qui peut annuler.
"""
from datetime import date as dt_date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.agent.tools.budget_models import BudgetEntryView

SessionId = Field(min_length=1, description="Session de l'appareil : lui seul peut annuler la saisie.")


def _required(value: str, what: str) -> str:
    if not value.strip():
        raise ValueError(f"{what} est vide.")
    return value.strip()


class BudgetFormEntry(BaseModel):
    """Formulaire Dépense / Revenu ; `categorie` = nom exact choisi dans la liste de l'écran."""
    type: Literal["depense", "revenu"]
    montant: float = Field(gt=0)
    categorie: str = Field(min_length=1)
    libelle: str = Field(description="Écrit « Otis : <libellé> » dans le classeur.")
    date: Optional[dt_date] = Field(None, description="Vide = aujourd'hui.")
    swile: bool = False
    remboursement: bool = False
    session_id: str = SessionId

    @field_validator("libelle")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        return _required(value, "Le libellé")

    @model_validator(mode="after")
    def _income_options(self) -> "BudgetFormEntry":
        if self.type == "revenu" and (self.swile or self.remboursement):
            raise ValueError("Un revenu ne peut être ni payé en Swile ni un remboursement.")
        return self


class InstallmentForm(BaseModel):
    """Formulaire Échéancier (format de `createInstallment` de l'Apps Script)."""
    type: Literal["echeancier"] = "echeancier"
    nom: str
    montant_total: float = Field(gt=0)
    nb_echeances: int = Field(ge=2)
    categorie: str = Field(min_length=1)
    mois_debut: Optional[str] = Field(
        None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="« 2026-12 » ; vide = mois en cours.",
    )
    commentaire: str = ""
    session_id: str = SessionId

    @field_validator("nom")
    @classmethod
    def _name(cls, value: str) -> str:
        return _required(value, "Le nom de l'échéancier")


class SplitPartForm(BaseModel):
    categorie: str = Field(min_length=1)
    montant: float = Field(gt=0)


class SplitExpenseForm(BaseModel):
    """Formulaire Dépense multiple (format de `createSplitTransaction`) ; la somme des parts est vérifiée à l'écriture."""
    type: Literal["multiple"] = "multiple"
    mot_cle: str = Field(description="Nom du marchand tel qu'il apparaîtra sur le relevé bancaire.")
    montant_total: float = Field(gt=0)
    parts: List[SplitPartForm] = Field(min_length=1)
    date: Optional[dt_date] = Field(None, description="Date prévue du débit ; vide = aujourd'hui.")
    session_id: str = SessionId

    @field_validator("mot_cle")
    @classmethod
    def _keyword(cls, value: str) -> str:
        return _required(value, "Le mot-clé bancaire")


class BudgetFormAck(BaseModel):
    message: str
    action_id: int = Field(description="Entrée du journal : à annuler via /api/v1/home/recent-actions/{id}/undo.")


class BudgetFormResult(BudgetFormAck):
    ligne: BudgetEntryView
