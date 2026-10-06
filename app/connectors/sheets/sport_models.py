"""Modèles de données Pydantic et calculs physiologiques pour le module Sport Running (Otis)."""
from datetime import date as dt_date
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


class SportSessionStatus(str, Enum):
    """Statut d'une séance dans le journal."""
    PLANIFIE = "Planifié"
    REALISE = "Réalisé"
    REPOS = "Repos"
    ANNULE = "Annulé"


class SportSessionType(str, Enum):
    """Type de séance d'entraînement."""
    EF = "EF"  # Endurance Fondamentale
    FRACTIONNE = "Fractionné"
    SORTIE_LONGUE = "Sortie Longue"
    TEMPO = "Tempo"
    RECUP = "Récup"
    RENFORCEMENT = "Renforcement"


def calculate_km_effort(distance_km: Optional[float], denivele_d_plus: Optional[int]) -> Optional[float]:
    """Calcule le Kilomètre-Effort standard : Distance (km) + D+ (m) / 100."""
    if distance_km is None:
        return None
    d_plus = max(denivele_d_plus or 0, 0)
    return round(float(distance_km) + (d_plus / 100.0), 2)


def calculate_speed_kmh(distance_km: Optional[float], duration_seconds: Optional[int]) -> Optional[float]:
    """Calcule la vitesse moyenne en km/h."""
    if not distance_km or not duration_seconds or duration_seconds <= 0:
        return None
    return round((float(distance_km) / duration_seconds) * 3600.0, 2)


def calculate_pace_min_km(distance_km: Optional[float], duration_seconds: Optional[int]) -> Optional[int]:
    """Calcule l'allure moyenne en secondes par kilomètre."""
    if not distance_km or not duration_seconds or duration_seconds <= 0 or distance_km <= 0:
        return None
    return int(round(duration_seconds / float(distance_km)))


def format_pace(pace_seconds: Optional[int]) -> Optional[str]:
    """Formate une allure en secondes vers la chaîne 'mm:ss'."""
    if pace_seconds is None or pace_seconds <= 0:
        return None
    minutes = pace_seconds // 60
    seconds = pace_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def calculate_rpe_load(duration_seconds: Optional[int], rpe: Optional[int]) -> int:
    """Calcule la charge d'entraînement de la séance (Session-RPE) : Durée (minutes) * RPE (1-10)."""
    if not duration_seconds or duration_seconds <= 0 or not rpe:
        return 0
    duration_minutes = duration_seconds / 60.0
    return int(round(duration_minutes * rpe))


class SportSession(BaseModel):
    """Représente une séance de course à pied dans l'onglet 'Seances'."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    date: dt_date
    semaine: int = Field(..., description="Numéro de semaine ISO (1-53)")
    statut: SportSessionStatus = SportSessionStatus.PLANIFIE
    type_seance: SportSessionType = SportSessionType.EF
    distance_km: Optional[float] = Field(None, ge=0.0)
    denivele_d_plus: Optional[int] = Field(0, ge=0)
    duree_secondes: Optional[int] = Field(None, ge=0)
    ressenti_rpe: Optional[int] = Field(None, ge=1, le=10)
    fc_moyenne: Optional[int] = Field(None, ge=30, le=250, description="Fréquence cardiaque moyenne (bpm)")
    fc_max: Optional[int] = Field(None, ge=30, le=250, description="Fréquence cardiaque maximale (bpm)")
    meteo_note: Optional[int] = Field(None, ge=1, le=10, description="Note difficulté météo de 1 à 10")
    programme: Optional[str] = Field(default="", description="Contenu technique : blocs fractionné, exercices renfo/kiné")
    remarques: Optional[str] = Field(default="", description="Bilan subjectif : sensations, alertes périostite, notes libres")
    notes: Optional[str] = ""
    strava_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def sync_programme_remarques_notes(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if data.get("notes") and not data.get("remarques"):
                data["remarques"] = data["notes"]
            elif data.get("remarques") and not data.get("notes"):
                data["notes"] = data["remarques"]
        return data

    @computed_field
    @property
    def km_effort(self) -> Optional[float]:
        return calculate_km_effort(self.distance_km, self.denivele_d_plus)

    @computed_field
    @property
    def vitesse_kmh(self) -> Optional[float]:
        return calculate_speed_kmh(self.distance_km, self.duree_secondes)

    @computed_field
    @property
    def allure_secondes(self) -> Optional[int]:
        return calculate_pace_min_km(self.distance_km, self.duree_secondes)

    @computed_field
    @property
    def allure_formatted(self) -> Optional[str]:
        return format_pace(self.allure_secondes)

    @computed_field
    @property
    def charge_rpe(self) -> Optional[int]:
        if self.ressenti_rpe and self.duree_secondes:
            return calculate_rpe_load(self.duree_secondes, self.ressenti_rpe)
        return None


class SportWeeklySummary(BaseModel):
    """Synthèse hebdomadaire et diagnostic sécurité du mini-coach dans l'onglet 'Synthese_Hebdo'."""
    semaine: int
    annee: int
    nb_seances: int = 0
    km_total: float = 0.0
    d_plus_total: int = 0
    km_effort_total: float = 0.0
    duree_secondes: int = 0
    charge_rpe_totale: int = 0
    nb_renfo: int = 0
    previous_week_km_effort: Optional[float] = None

    @computed_field
    @property
    def allure_moyenne_formatted(self) -> Optional[str]:
        if self.km_total > 0 and self.duree_secondes > 0:
            pace_sec = calculate_pace_min_km(self.km_total, self.duree_secondes)
            return format_pace(pace_sec)
        return None

    @computed_field
    @property
    def evolution_charge_pct(self) -> Optional[float]:
        if self.previous_week_km_effort and self.previous_week_km_effort > 0:
            diff = self.km_effort_total - self.previous_week_km_effort
            return round((diff / self.previous_week_km_effort) * 100.0, 1)
        return None

    @computed_field
    @property
    def alerte_securite(self) -> str:
        if self.evolution_charge_pct is None:
            return "⚪ Première semaine enregistrée"
        if self.evolution_charge_pct <= 10.0:
            return f"🟢 Progression Saine (+{self.evolution_charge_pct:.1f}%)"
        if self.evolution_charge_pct <= 15.0:
            return f"🟡 Vigilance (+{self.evolution_charge_pct:.1f}%)"
        return f"🔴 Risque Blessure (> +15% : +{self.evolution_charge_pct:.1f}%)"

    @computed_field
    @property
    def plafond_conseille_s_plus_1(self) -> float:
        """Plafond maximal d'augmentation recommandé pour S+1 (+10% max en Km-Effort)."""
        ref_km_effort = self.km_effort_total if self.km_effort_total > 0 else (self.previous_week_km_effort or 0.0)
        return round(ref_km_effort * 1.10, 1)


class SportSessionCreate(BaseModel):
    """Payload pour enregistrer une séance réalisée."""
    date: Optional[dt_date] = None
    type_seance: SportSessionType = SportSessionType.EF
    distance_km: Optional[float] = Field(None, ge=0.0)
    duree_secondes: int = Field(..., gt=0)
    denivele_d_plus: Optional[int] = Field(0, ge=0)
    ressenti_rpe: Optional[int] = Field(None, ge=1, le=10)
    fc_moyenne: Optional[int] = Field(None, ge=30, le=250, description="Fréquence cardiaque moyenne (bpm)")
    fc_max: Optional[int] = Field(None, ge=30, le=250, description="Fréquence cardiaque maximale (bpm)")
    meteo_note: Optional[int] = Field(None, ge=1, le=10)
    programme: Optional[str] = ""
    remarques: Optional[str] = ""
    notes: Optional[str] = ""
    strava_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def sync_notes_create(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if data.get("notes") and not data.get("remarques"):
                data["remarques"] = data["notes"]
            elif data.get("remarques") and not data.get("notes"):
                data["notes"] = data["remarques"]
        return data


class SportSessionUpdate(BaseModel):
    """Payload pour modifier une séance passée (RPE, notes de douleur, ressenti)."""
    ressenti_rpe: Optional[int] = Field(None, ge=1, le=10)
    programme: Optional[str] = None
    remarques: Optional[str] = None
    notes: Optional[str] = None
    append_remarques: bool = False
    append_notes: bool = False
    type_seance: Optional[SportSessionType] = None
    distance_km: Optional[float] = Field(None, ge=0.0)
    denivele_d_plus: Optional[int] = Field(None, ge=0)
    duree_secondes: Optional[int] = Field(None, ge=0)
    fc_moyenne: Optional[int] = Field(None, ge=30, le=250)
    fc_max: Optional[int] = Field(None, ge=30, le=250)
    meteo_note: Optional[int] = Field(None, ge=1, le=10)

    @model_validator(mode="before")
    @classmethod
    def sync_notes_update(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if data.get("notes") is not None and data.get("remarques") is None:
                data["remarques"] = data["notes"]
            if data.get("append_notes") and not data.get("append_remarques"):
                data["append_remarques"] = True
        return data


class SportSessionPlan(BaseModel):
    """Payload pour planifier une séance future."""
    date: dt_date
    type_seance: SportSessionType = SportSessionType.EF
    distance_km_cible: Optional[float] = Field(None, gt=0.0)
    duree_cible_secondes: Optional[int] = Field(None, gt=0)
    programme: Optional[str] = ""
    remarques: Optional[str] = ""
    notes: Optional[str] = ""

    @model_validator(mode="before")
    @classmethod
    def sync_notes_plan(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if data.get("notes") and not data.get("programme"):
                data["programme"] = data["notes"]
        return data



