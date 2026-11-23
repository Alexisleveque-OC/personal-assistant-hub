"""Contrats Pydantic des outils Budget de l'agent : arguments stricts et vues renvoyées au modèle."""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

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
