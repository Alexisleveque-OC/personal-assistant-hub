"""Contrats Pydantic des outils Budget de l'agent : arguments stricts, vues renvoyées au modèle et annulations."""
from datetime import date as dt_date
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

from app.connectors.sheets.budget_models import BudgetEntry, BudgetMonth, EntrySheet, NewInstallment, SplitExpense
from app.core.agent.tools.sport_models import StrictArgs

# « appris » : nom de catégorie appris par la réponse à une question « lequel ? » (étape 5 bis)
Match = Literal["exact", "tri_auto", "nom_proche", "appris"]
LEARNED_DESCRIPTION = (
    "Non vide : Otis vient d'apprendre ce nom de catégorie ; annonce-le en une phrase "
    "(« Je retiendrai que … , c'est … »)."
)


class GetBudgetRemainingArgs(StrictArgs):
    categorie: str = Field(description="Catégorie ou groupe tel que dit par l'utilisateur (« course », « loisir »).")
    mois: Optional[int] = Field(None, ge=1, le=12, description="Mois visé ; par défaut le mois actif du budget.")
    annee: Optional[int] = Field(None, description="Année du mois visé ; par défaut celle du mois actif.")


class BudgetRemainingView(BaseModel):
    categorie: str
    categorie_dite: str
    rapprochement: Match
    reste_total: float
    annonce_total: str = Field(description="Phrase à dire pour le reste total (signe déjà interprété).")
    mois: str
    reste_du_mois: float
    annonce_du_mois: str = Field(description="Phrase à dire pour le reste du mois (signe déjà interprété).")
    categories_du_groupe: List[str] = Field(
        default_factory=list, description="Non vide : la catégorie est un groupe, restes = somme de ces catégories.",
    )
    nom_appris: Optional[str] = Field(None, description=LEARNED_DESCRIPTION)


class GetIncomeArgs(StrictArgs):
    type: Optional[str] = Field(None, description="Type de revenu (« CAF », « salaire Alexis ») ; absent = tous.")
    mois: int = Field(ge=1, le=12)
    annee: int


class IncomeView(BaseModel):
    type: Optional[str]
    mois: str
    total: float
    nombre: int
    nom_appris: Optional[str] = Field(None, description=LEARNED_DESCRIPTION)


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
    rapprochement: Match


class BudgetEntryAddedUndo(BaseModel):
    kind: Literal["budget_entry_added"] = "budget_entry_added"
    entry: BudgetEntry


class BudgetCategoryChangedUndo(BaseModel):
    """`entry` : ligne telle que laissée par la correction ; l'annulation remet `previous_category`."""
    kind: Literal["budget_category_changed"] = "budget_category_changed"
    entry: BudgetEntry
    previous_category: str


# --- Échéanciers et dépenses multiples (étape 4) --------------------------------------------------------

def _required_text(value: str, what: str) -> str:
    if not value.strip():
        raise ValueError(f"{what} est vide.")
    return value.strip()


class AddInstallmentArgs(StrictArgs):
    nom: str = Field(description="Nom du magasin ou de l'achat tel que dit (« ikea », « frigo »).")
    montant_total: float = Field(gt=0, description="Montant total en euros.")
    nb_echeances: int = Field(ge=2, description="Nombre de paiements (« en 4 fois » → 4).")
    categorie: str = Field(description="Catégorie de dépense telle que dite par l'utilisateur.")
    mois_debut: Optional[int] = Field(
        None, ge=1, le=12, description="Mois de la 1re échéance seulement s'il est dit ; sinon le mois en cours.",
    )
    annee_debut: Optional[int] = Field(None, description="Année de la 1re échéance seulement si elle est dite.")
    commentaire: str = Field("", description="Précision dite (« le canapé ») ; sinon vide.")

    @field_validator("nom")
    @classmethod
    def _name(cls, value: str) -> str:
        return _required_text(value, "Le nom de l'échéancier")


class SplitPartArgs(StrictArgs):
    categorie: str = Field(description="Catégorie de cette part telle que dite.")
    montant: float = Field(gt=0, description="Montant de cette part en euros.")


class PredeclareSplitExpenseArgs(StrictArgs):
    mot_cle: str = Field(
        description="Nom du marchand tel qu'il apparaîtra sur le relevé bancaire (« amazon », « leclerc »).",
    )
    montant_total: float = Field(gt=0, description="Montant total qui sera débité, en euros.")
    parts: List[SplitPartArgs] = Field(min_length=1, description="Chaque catégorie et son montant ; somme = total.")
    date: Optional[dt_date] = Field(None, description="Date prévue du débit seulement si elle est dite ; sinon aujourd'hui.")

    @field_validator("mot_cle")
    @classmethod
    def _keyword(cls, value: str) -> str:
        return _required_text(value, "Le mot-clé bancaire")



class SplitPartView(BaseModel):
    categorie: str
    montant: float
    rapprochement: Match


class SplitExpenseView(BaseModel):
    date: dt_date
    mot_cle: str
    montant_total: float
    parts: List[SplitPartView]
    statut: str = Field(description="« A traiter » : l'import découpera le débit correspondant (±3 jours).")


class InstallmentAddedUndo(BaseModel):
    kind: Literal["budget_installment_added"] = "budget_installment_added"
    installment: NewInstallment


class SplitDeclaredUndo(BaseModel):
    kind: Literal["budget_split_declared"] = "budget_split_declared"
    split: SplitExpense


class BudgetAliasLearnedUndo(BaseModel):
    """Nom de catégorie appris avec l'écriture : « annule » juste après l'oublie aussi (décision du 24/11)."""
    kind: Literal["budget_alias_learned"] = "budget_alias_learned"
    alias: str
    category: str


class InstallmentMutation(BaseModel):
    action: Literal["echeancier_ajoute"] = "echeancier_ajoute"
    echeancier: InstallmentView
    rapprochement: Match
    nom_appris: Optional[str] = Field(None, description=LEARNED_DESCRIPTION)
    undos: List[Union[InstallmentAddedUndo, BudgetAliasLearnedUndo]]


class SplitMutation(BaseModel):
    action: Literal["depense_multiple_predeclaree"] = "depense_multiple_predeclaree"
    depense: SplitExpenseView
    nom_appris: Optional[str] = Field(None, description=LEARNED_DESCRIPTION)
    undos: List[Union[SplitDeclaredUndo, BudgetAliasLearnedUndo]]


class SwileBalanceChange(BaseModel):
    """Case « Reste Swile » remplacée par l'import : l'annulation remet `previous` (None = case vide)."""
    month: BudgetMonth
    previous: Optional[float] = None
    written: float


class SwileImportUndo(BaseModel):
    """Import Swile entier (étape 8) : annulé d'un coup, refusé si une de ses lignes ou le solde a changé depuis."""
    kind: Literal["budget_swile_import"] = "budget_swile_import"
    entries: List[BudgetEntry] = Field(default_factory=list)
    balance: Optional[SwileBalanceChange] = None


BudgetUndo = Union[
    BudgetEntryAddedUndo, BudgetCategoryChangedUndo, InstallmentAddedUndo, SplitDeclaredUndo, SwileImportUndo,
]


class ForgetBudgetAliasArgs(StrictArgs):
    nom: str = Field(description="Nom de catégorie appris à oublier, tel que dit (« oublie loisir alexis »).")


class ForgottenAliasView(BaseModel):
    action: Literal["nom_appris_oublie"] = "nom_appris_oublie"
    nom: str
    categorie: str


class BudgetMutation(BaseModel):
    action: Literal["depense_ajoutee", "remboursement_ajoute", "revenu_ajoute", "categorie_corrigee"]
    ligne: BudgetEntryView
    ancienne_categorie: Optional[str] = None
    nom_appris: Optional[str] = Field(None, description=LEARNED_DESCRIPTION)
    undos: List[Union[BudgetUndo, BudgetAliasLearnedUndo]]
