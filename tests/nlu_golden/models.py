"""Contrats Pydantic du jeu de référence NLU (golden set).

Un cas = carnet d'entraînement et classeur Repas & Courses initiaux + phrase(s) de l'utilisateur → effet attendu.
Les dates sont relatives à « aujourd'hui » (`day_offset`) : aucun figement d'horloge nécessaire.
"""
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.connectors.sheets.sport_models import SportSessionStatus, SportSessionType

# Valeurs attendues par champ de `sport_sessions`. Suffixe `__contains` : sous-chaîne insensible à la casse.
# Clé spéciale `day_offset` : date attendue relative à aujourd'hui.
FieldExpectations = Dict[str, Union[str, int, float]]


class SeedSession(BaseModel):
    """Séance présente dans le carnet avant l'échange, désignée par un alias stable (`ref`)."""
    model_config = ConfigDict(extra="forbid")

    ref: str = Field(pattern=r"^[a-z0-9_]+$")
    day_offset: int = Field(description="Décalage en jours par rapport à aujourd'hui (0 = aujourd'hui).")
    type_seance: SportSessionType
    statut: SportSessionStatus = SportSessionStatus.REALISE
    distance_km: Optional[float] = None
    duree_secondes: Optional[int] = None
    ressenti_rpe: Optional[int] = None
    meteo_note: Optional[int] = None


class SeedShoppingItem(BaseModel):
    """Article présent avant l'échange, dans la liste d'attente ou dans la liste de la semaine."""
    model_config = ConfigDict(extra="forbid")

    nom: str = Field(min_length=1)
    coche: bool = False
    liste: Literal["attente", "semaine"] = "attente"
    rayon: str = Field("Épicerie", description="Rayon d'affichage (liste de la semaine uniquement).")


class SeedMeal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day_offset: int
    midi: str = ""
    soir: str = ""


class ExpectedMeal(BaseModel):
    """Repas modifié attendu ; tout autre créneau du planning doit rester inchangé."""
    model_config = ConfigDict(extra="forbid")

    day_offset: int
    moment: Literal["midi", "soir"]
    plat__contains: str = Field(min_length=1)


class ExpectedOutcome(BaseModel):
    """Effet attendu. Toute séance, tout article et tout repas non cités doivent rester strictement inchangés.

    Les noms d'articles sont comparés sans casse, accents, article initial ni pluriel simple.
    """
    model_config = ConfigDict(extra="forbid")

    updated: Dict[str, FieldExpectations] = Field(default_factory=dict)
    created: List[FieldExpectations] = Field(default_factory=list)
    courses_ajoutees: List[str] = Field(default_factory=list)
    courses_cochees: List[str] = Field(default_factory=list)
    courses_retirees: List[str] = Field(default_factory=list)
    repas_modifies: List[ExpectedMeal] = Field(default_factory=list)
    rayons_appris: Dict[str, str] = Field(
        default_factory=dict, description="Lignes ajoutées à Ingredients_Rayons : article → rayon (vide = à trier).",
    )
    clarification: bool = Field(
        False, description="Aucune mutation, et la dernière réponse pose une question à l'utilisateur."
    )
    notes_created: Optional[int] = Field(None, description="Nombre de notes attendues (None = non vérifié).")
    notes_francais: bool = Field(False, description="Les notes créées doivent être rédigées en français.")
    notes_contiennent: List[str] = Field(
        default_factory=list, description="Mots que chaque note créée doit contenir (insensible à la casse).",
    )
    response_includes: List[str] = Field(default_factory=list)
    response_excludes: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def clarification_has_no_mutation(self) -> "ExpectedOutcome":
        sheet_changes = (
            self.courses_ajoutees or self.courses_cochees or self.courses_retirees or self.repas_modifies or self.rayons_appris
        )
        if self.clarification and (self.updated or self.created or sheet_changes):
            raise ValueError("Un cas de clarification ne peut pas attendre de mutation du carnet.")
        return self


class GoldenCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9-]+$")
    origine: str = Field(min_length=1, description="Échec ou comportement de prod reproduit (réécrit, anonymisé).")
    carnet: List[SeedSession] = Field(default_factory=list)
    courses: List[SeedShoppingItem] = Field(default_factory=list)
    repas: List[SeedMeal] = Field(default_factory=list)
    turns: List[str] = Field(min_length=1)
    expected: ExpectedOutcome

    @model_validator(mode="after")
    def refs_are_consistent(self) -> "GoldenCase":
        refs = [s.ref for s in self.carnet]
        if len(refs) != len(set(refs)):
            raise ValueError(f"[{self.id}] alias de séance dupliqués : {refs}")
        unknown = set(self.expected.updated) - set(refs)
        if unknown:
            raise ValueError(f"[{self.id}] séances attendues absentes du carnet : {sorted(unknown)} (connues : {refs})")
        return self
