"""Modèles Pydantic du classeur Budget : contrats lus et écrits par `BudgetConnector`."""
import json
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


class RecordedEntry(BaseModel):
    """Ligne déjà présente dans `Swile` ou `Revenus` (recherche de doublons de l'import Swile)."""
    day: date
    amount: float
    category: str


class SwileBalance(BaseModel):
    """Case « Reste Swile » de `Gestion`, colonne Prévu du mois ; `value` None si la case est vide."""
    month: BudgetMonth
    value: Optional[float] = None


class NewInstallment(BaseModel):
    """Échéancier écrit par Otis dans `Échéanciers` (format de `createInstallment` : échéance actuelle 0, Actif).

    L'import bancaire le rapproche par mois attendu et mensualité (±0,05 €), pas par son nom.
    """
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    total_amount: float = Field(gt=0)
    count: int = Field(ge=1)
    start_month: BudgetMonth
    category: str = Field(min_length=1)
    comment: str = ""

    @property
    def monthly_amount(self) -> float:
        """Arrondi au centime, demi vers le haut (`Math.round(total / count * 100) / 100` de l'Apps Script)."""
        exact = Decimal(str(self.total_amount)) / Decimal(self.count)
        return float(exact.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class SplitPart(BaseModel):
    """Part d'une dépense multiple : catégorie exacte du classeur et montant positif."""
    model_config = ConfigDict(frozen=True)

    category: str = Field(min_length=1)
    amount: float = Field(gt=0)


class SplitExpense(BaseModel):
    """Dépense multiple pré-déclarée dans `Dépenses Multiples` (format de `createSplitTransaction`, statut « A traiter »).

    L'import la découpe quand un débit du même montant (±0,05 €) contenant `keyword` arrive à ±3 jours de `day`.
    """
    model_config = ConfigDict(frozen=True)

    day: date
    keyword: str = Field(min_length=1, description="Mot-clé du libellé bancaire, sans préfixe (sert au rapprochement).")
    total_amount: float = Field(gt=0)
    parts: Tuple[SplitPart, ...] = Field(min_length=1)

    @field_validator("keyword")
    @classmethod
    def _strip_keyword(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Le mot-clé bancaire est vide.")
        return value.strip()

    @model_validator(mode="after")
    def _parts_add_up(self) -> "SplitExpense":
        allotted = round(sum(part.amount for part in self.parts), 2)
        if allotted != round(self.total_amount, 2):
            raise ValueError(
                f"Le montant total ({self.total_amount:.2f} €) diffère de la somme des parts ({allotted:.2f} €) : "
                f"écart de {round(self.total_amount - allotted, 2):.2f} €."
            )
        return self

    @property
    def description(self) -> str:
        return " | ".join(f"{part.category} : {part.amount:.2f} €" for part in self.parts)

    @property
    def parts_json(self) -> str:
        """Comme `JSON.stringify` : sans espaces, accents tels quels, montant entier sans « .0 »."""
        return json.dumps(
            [{"category": part.category, "amount": _js_number(part.amount)} for part in self.parts],
            ensure_ascii=False, separators=(",", ":"),
        )


def _js_number(value: float) -> float | int:
    return int(value) if float(value).is_integer() else value


class BudgetCategoryLine(BaseModel):
    """Catégorie de l'écran Budget : reste total (colonne B de `Gestion`) et suivi du mois actif.

    `month_budget` = Prévu + Equilibrage du mois dans `Gestion` ; `month_spent` = sa ligne de `Total dépenses`
    (pour une catégorie de revenus : prévu et reçu).
    """
    name: str
    total_remaining: float
    month_spent: float
    month_budget: float


class BudgetGroup(BaseModel):
    """Groupe de `Gestion` (Courants, Loisir…) ; `total_remaining` couvre toutes ses catégories, même masquées."""
    name: str
    total_remaining: float
    categories: List[BudgetCategoryLine]


class MonthlyTotals(BaseModel):
    """Lignes « Total dépense » et « Total revenus » de `Total dépenses` pour un mois."""
    month: BudgetMonth
    expenses: float
    income: float


class BudgetOverview(BaseModel):
    """Écran Budget (lecture seule) : mois actif, épargné du mois, série de l'année jusqu'au mois actif, groupes."""
    active_month: BudgetMonth
    saved: float
    series: List[MonthlyTotals]
    groups: List[BudgetGroup]
    income_categories: List[str] = Field(description="Types de revenu actifs (groupe Revenus) : choix du formulaire.")
