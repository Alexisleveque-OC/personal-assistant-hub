"""Modèles Pydantic du classeur Budget : contrats lus et écrits par `BudgetConnector`."""
from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

FRENCH_MONTHS = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)


class BudgetMonth(BaseModel):
    """Mois budgétaire (le classeur raisonne par mois calendaire)."""
    model_config = ConfigDict(frozen=True)

    year: int
    month: int = Field(ge=1, le=12)

    @property
    def label(self) -> str:
        return f"{FRENCH_MONTHS[self.month - 1]} {self.year}"

    def previous(self) -> "BudgetMonth":
        if self.month == 1:
            return BudgetMonth(year=self.year - 1, month=12)
        return BudgetMonth(year=self.year, month=self.month - 1)

    def contains(self, day: date) -> bool:
        return (day.year, day.month) == (self.year, self.month)


class BudgetCategory(BaseModel):
    """Ligne de l'onglet `Catégories` ; `name` est conservé à l'identique (liste déroulante du classeur)."""
    name: str
    created: Optional[date] = None
    ended: Optional[date] = None

    def is_active(self, today: date) -> bool:
        return self.ended is None or self.ended >= today


class AutoSortRule(BaseModel):
    """Ligne de l'onglet `Tri auto` : mot-clé du libellé bancaire → catégorie."""
    keyword: str
    category: str


class CategoryRemaining(BaseModel):
    """Reste d'une catégorie (ou d'un groupe) dans `Gestion` : reste total (colonne B) et reste fin du mois.

    Pour un groupe (Loisir, Courants…), somme de ses catégories, listées dans `group_categories`.
    """
    category: str
    total_remaining: float
    month: BudgetMonth
    month_remaining: float
    group_categories: List[str] = Field(default_factory=list)


class IncomeSummary(BaseModel):
    """Somme des revenus d'un type (tous si None) sur un mois (onglet `Revenus`)."""
    income_type: Optional[str]
    month: BudgetMonth
    total: float
    count: int


class Installment(BaseModel):
    """Ligne de l'onglet `Échéanciers`."""
    name: str
    total_amount: float
    installments_count: int
    current_installment: int
    monthly_amount: float
    start_month: BudgetMonth
    category: str
    comment: str = ""
    status: str

    @property
    def remaining_count(self) -> int:
        return max(self.installments_count - self.current_installment, 0)

    @property
    def remaining_amount(self) -> float:
        return round(self.remaining_count * self.monthly_amount, 2)


class CategoryResolution(BaseModel):
    """Rapprochement d'une catégorie dictée : jamais d'invention, une question si plusieurs choix sont possibles."""
    spoken: str
    status: Literal["resolved", "ambiguous", "unknown"]
    category: Optional[str] = None
    source: Optional[Literal["category", "auto_sort", "close_match"]] = None
    candidates: List[str] = Field(default_factory=list)


EntrySheet = Literal["Débit", "Swile", "Revenus"]


class BudgetEntry(BaseModel):
    """Ligne de saisie écrite par Otis (dépense, remboursement négatif, revenu) : de quoi la retrouver par son contenu."""
    model_config = ConfigDict(frozen=True)

    sheet: EntrySheet
    day: date
    amount: float
    category: str = Field(min_length=1)
    label: str = Field(min_length=1, description="« Otis : <libellé dicté> » (Intitulé, ou Commentaires pour Swile).")
