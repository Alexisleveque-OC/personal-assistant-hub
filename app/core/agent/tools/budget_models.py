"""Contrats Pydantic des outils Budget de l'agent : arguments stricts, vues renvoyées au modèle et annulations."""
from datetime import date as dt_date
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

from app.connectors.sheets.budget_models import BudgetEntry, EntrySheet
from app.core.agent.tools.sport_models import StrictArgs


class GetBudgetRemainingArgs(StrictArgs):
    categorie: str = Field(description="Catégorie ou groupe tel que dit par l'utilisateur (« course », « loisir »).")
    mois: Optional[int] = Field(None, ge=1, le=12, description="Mois visé ; par défaut le mois actif du budget.")
    annee: Optional[int] = Field(None, description="Année du mois visé ; par défaut celle du mois actif.")


class BudgetRemainingView(BaseModel):
    categorie: str
    categorie_dite: str
    rapprochement: Literal["exact", "tri_auto", "nom_proche"]
    reste_total: float
    annonce_total: str = Field(description="Phrase à dire pour le reste total (signe déjà interprété).")
    mois: str
    reste_du_mois: float
    annonce_du_mois: str = Field(description="Phrase à dire pour le reste du mois (signe déjà interprété).")
    categories_du_groupe: List[str] = Field(
        default_factory=list, description="Non vide : la catégorie est un groupe, restes = somme de ces catégories.",
    )


class GetIncomeArgs(StrictArgs):
    type: Optional[str] = Field(None, description="Type de revenu (« CAF », « salaire Alexis ») ; absent = tous.")
    mois: int = Field(ge=1, le=12)
    annee: int


class IncomeView(BaseModel):
    type: Optional[str]
    mois: str
    total: float
    nombre: int


class GetInstallmentsArgs(StrictArgs):
    nom: Optional[str] = Field(None, description="Nom d'un échéancier à suivre ; absent = tous les échéanciers actifs.")


class InstallmentView(BaseModel):
    nom: str
    categorie: str
    mensualite: float
    echeance_actuelle: int
    nb_echeances: int
    echeances_restantes: int
    montant_restant: float
    mois_debut: str
    statut: str
    commentaire: str = ""


class InstallmentsView(BaseModel):
    echeanciers: List[InstallmentView]


# --- Écritures (étape 3) -------------------------------------------------------------------------------

class _EntryArgs(StrictArgs):
    montant: float = Field(gt=0, description="Montant positif en euros, tel que dit.")
    libelle: str = Field(
        description="Ce sur quoi porte l'opération, tel que dit (« pizza chez Mario »), sinon la catégorie dite.",
    )
    date: Optional[dt_date] = Field(None, description="Jour de l'opération seulement s'il est dit ; sinon aujourd'hui.")

    @field_validator("libelle")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Le libellé est vide.")
        return value.strip()


class AddExpenseArgs(_EntryArgs):
    categorie: str = Field(description="Catégorie de dépense telle que dite par l'utilisateur (« course », « resto »).")
    swile: bool = Field(False, description="Payé en Swile / ticket resto (sinon : compte bancaire).")
    remboursement: bool = Field(False, description="Remboursement reçu (« je me suis fait rembourser ») : ligne négative.")


class AddIncomeArgs(_EntryArgs):
    type: str = Field(description="Type de revenu tel que dit (« CAF », « salaire Alexis »).")


class CorrectBudgetCategoryArgs(StrictArgs):
    categorie: str = Field(description="Bonne catégorie dite par l'utilisateur (« non, c'était dans X »).")


class BudgetEntryView(BaseModel):
    onglet: EntrySheet
    date: dt_date
    montant: float = Field(description="Négatif pour un remboursement.")
    categorie: str
    intitule: str
    rapprochement: Literal["exact", "tri_auto", "nom_proche"]


class BudgetEntryAddedUndo(BaseModel):
    kind: Literal["budget_entry_added"] = "budget_entry_added"
    entry: BudgetEntry


class BudgetCategoryChangedUndo(BaseModel):
    """`entry` : ligne telle que laissée par la correction ; l'annulation remet `previous_category`."""
    kind: Literal["budget_category_changed"] = "budget_category_changed"
    entry: BudgetEntry
    previous_category: str


BudgetUndo = Union[BudgetEntryAddedUndo, BudgetCategoryChangedUndo]


class BudgetMutation(BaseModel):
    action: Literal["depense_ajoutee", "remboursement_ajoute", "revenu_ajoute", "categorie_corrigee"]
    ligne: BudgetEntryView
    ancienne_categorie: Optional[str] = None
    undos: List[BudgetUndo]
