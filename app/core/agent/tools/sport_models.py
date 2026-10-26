"""Contrats Pydantic stricts des outils sport de l'agent (arguments, vues et instantanés)."""
from datetime import date as dt_date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.connectors.sheets.sport_models import SportSession, SportSessionStatus, SportSessionType

WEEKDAYS_FR = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


class StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FindSessionsArgs(StrictArgs):
    """Recherche de séances, les plus récentes d'abord."""
    date_from: Optional[dt_date] = None
    date_to: Optional[dt_date] = None
    type_seance: Optional[SportSessionType] = None
    statut: Optional[SportSessionStatus] = None
    limit: int = Field(10, ge=1, le=50)

    @model_validator(mode="after")
    def range_is_ordered(self) -> "FindSessionsArgs":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError(f"date_from ({self.date_from}) doit précéder date_to ({self.date_to}).")
        return self


class GetSessionArgs(StrictArgs):
    session_id: int = Field(gt=0, description="Identifiant de la séance.")


class SessionChanges(StrictArgs):
    """Champs à modifier sur une séance existante ; seuls les champs renseignés sont appliqués."""
    date: Optional[dt_date] = None
    statut: Optional[SportSessionStatus] = None
    type_seance: Optional[SportSessionType] = None
    distance_km: Optional[float] = Field(None, ge=0.0)
    duree_secondes: Optional[int] = Field(None, ge=0, description="Durée en secondes.")
    denivele_d_plus: Optional[int] = Field(None, ge=0)
    ressenti_rpe: Optional[int] = Field(None, ge=1, le=10, description="Ressenti d'effort (RPE) de 1 à 10.")
    fc_moyenne: Optional[int] = Field(None, ge=30, le=250, description="Fréquence cardiaque moyenne (bpm).")
    fc_max: Optional[int] = Field(None, ge=30, le=250, description="Fréquence cardiaque maximale (bpm).")
    meteo_note: Optional[int] = Field(None, ge=1, le=10, description="Difficulté liée à la météo de 1 (idéale) à 10.")
    programme: Optional[str] = None
    remarques: Optional[str] = Field(None, description="Ressenti libre (sensations, douleurs), en français.")

    @model_validator(mode="after")
    def at_least_one_change(self) -> "SessionChanges":
        if not self.model_dump(exclude_none=True):
            raise ValueError("Indiquer au moins un champ à modifier.")
        return self


class UpdateSessionArgs(StrictArgs):
    session_id: int = Field(gt=0, description="Identifiant de la séance existante à modifier.")
    changes: SessionChanges


class LogSessionArgs(StrictArgs):
    """Séance réalisée à créer. Aucune valeur n'est déduite : ce qui n'est pas dit reste vide."""
    date: dt_date
    type_seance: SportSessionType
    distance_km: Optional[float] = Field(None, ge=0.0)
    duree_secondes: Optional[int] = Field(None, ge=0, description="Durée en secondes.")
    denivele_d_plus: Optional[int] = Field(None, ge=0)
    ressenti_rpe: Optional[int] = Field(None, ge=1, le=10, description="Ressenti d'effort (RPE) de 1 à 10.")
    fc_moyenne: Optional[int] = Field(None, ge=30, le=250, description="Fréquence cardiaque moyenne (bpm).")
    fc_max: Optional[int] = Field(None, ge=30, le=250, description="Fréquence cardiaque maximale (bpm).")
    meteo_note: Optional[int] = Field(None, ge=1, le=10, description="Difficulté liée à la météo de 1 (idéale) à 10.")
    programme: Optional[str] = None
    remarques: Optional[str] = Field(None, description="Ressenti libre (sensations, douleurs), en français.")


class PlanSessionArgs(StrictArgs):
    """Séance future à planifier."""
    date: dt_date
    type_seance: SportSessionType
    distance_km: Optional[float] = Field(None, ge=0.0)
    duree_secondes: Optional[int] = Field(None, gt=0)
    programme: Optional[str] = None
    remarques: Optional[str] = Field(None, description="Ressenti libre (sensations, douleurs), en français.")
    allure_cible: Optional[str] = Field(None, description="Allure cible, ex. 06:15/km.")
    vitesse_cible: Optional[str] = Field(None, description="Vitesse cible, ex. 9.6 km/h.")


class SessionView(BaseModel):
    """Vue compacte d'une séance, identifiant compris, telle que présentée au LLM."""
    id: int
    date: dt_date
    jour: str
    statut: SportSessionStatus
    type_seance: SportSessionType
    distance_km: Optional[float] = None
    duree_secondes: Optional[int] = None
    ressenti_rpe: Optional[int] = None
    meteo_note: Optional[int] = None
    fc_moyenne: Optional[int] = None
    fc_max: Optional[int] = None
    programme: str = ""
    remarques: str = ""

    @classmethod
    def from_session(cls, session: SportSession) -> "SessionView":
        if session.id is None:
            raise ValueError(f"Séance du {session.date} sans identifiant : impossible de la référencer.")
        return cls(
            id=session.id,
            date=session.date,
            jour=WEEKDAYS_FR[session.date.weekday()],
            statut=session.statut,
            type_seance=session.type_seance,
            distance_km=session.distance_km,
            duree_secondes=session.duree_secondes,
            ressenti_rpe=session.ressenti_rpe,
            meteo_note=session.meteo_note,
            fc_moyenne=session.fc_moyenne,
            fc_max=session.fc_max,
            programme=session.programme or "",
            remarques=session.remarques or "",
        )


class SessionRow(BaseModel):
    """Copie brute d'une ligne `sport_sessions` (sans normalisation) pour une restauration exacte."""
    id: int
    date: str
    semaine: int
    statut: str
    type_seance: str
    distance_km: Optional[float] = None
    denivele_d_plus: Optional[int] = None
    duree_secondes: Optional[int] = None
    ressenti_rpe: Optional[int] = None
    fc_moyenne: Optional[int] = None
    fc_max: Optional[int] = None
    meteo_note: Optional[int] = None
    programme: Optional[str] = None
    remarques: Optional[str] = Field(None, description="Ressenti libre (sensations, douleurs), en français.")
    notes: Optional[str] = None
    allure_cible: Optional[str] = None
    vitesse_cible: Optional[str] = None
    strava_id: Optional[str] = None


class UndoSnapshot(BaseModel):
    """Instantané permettant d'annuler une mutation : `before` est None pour une création.

    `after` (état juste après la mutation) permet de refuser l'annulation si la séance a été modifiée depuis.
    """
    kind: Literal["sport_session"] = "sport_session"
    action: Literal["created", "updated"]
    session_id: int
    before: Optional[SessionRow] = None
    after: SessionRow

    @model_validator(mode="after")
    def before_matches_action(self) -> "UndoSnapshot":
        if (self.action == "updated") != (self.before is not None):
            raise ValueError("Un instantané 'updated' exige l'état précédent, un 'created' n'en a pas.")
        return self


class MutationResult(BaseModel):
    session: SessionView
    undo: UndoSnapshot
