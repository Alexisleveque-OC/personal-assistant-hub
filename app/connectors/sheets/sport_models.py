"""Modèles de données Pydantic et calculs physiologiques pour le module Sport Running (Otis)."""
from datetime import date as dt_date
from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator


class SportSessionStatus(str, Enum):
    """Statut d'une séance dans le journal."""
    PLANIFIE = "Prévu"
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
    allure_cible: Optional[str] = Field(default=None, description="Allure cible conseillée (ex: 06:30/km (+/- 15s))")
    vitesse_cible: Optional[str] = Field(default=None, description="Vitesse cible conseillée (ex: 9.2 km/h (+/- 0.4 km/h))")
    strava_id: Optional[str] = None

    @field_validator("statut", mode="before")
    @classmethod
    def normalize_statut(cls, val: Any) -> Any:
        if isinstance(val, str):
            clean = val.strip().lower()
            if "réalisé" in clean or "realise" in clean:
                return SportSessionStatus.REALISE
            if "repos" in clean:
                return SportSessionStatus.REPOS
            if "annulé" in clean or "annule" in clean:
                return SportSessionStatus.ANNULE
            if "planifié" in clean or "planifie" in clean or "prévu" in clean or "prevu" in clean:
                return SportSessionStatus.PLANIFIE
        return val

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
    vitesse_moyenne_kmh: Optional[float] = None
    previous_week_vitesse_kmh: Optional[float] = None
    previous_week_charge_rpe: Optional[int] = None
    duree_course_secondes: Optional[int] = Field(None, description="Durée cumulée des séances de course uniquement (hors renfo)")

    @computed_field
    @property
    def allure_moyenne_formatted(self) -> Optional[str]:
        dur = self.duree_course_secondes if (self.duree_course_secondes and self.duree_course_secondes > 0) else self.duree_secondes
        if self.km_total > 0 and dur > 0:
            pace_sec = calculate_pace_min_km(self.km_total, dur)
            return format_pace(pace_sec)
        return None

    @computed_field
    @property
    def vitesse_kmh(self) -> Optional[float]:
        if self.vitesse_moyenne_kmh is not None:
            return self.vitesse_moyenne_kmh
        dur = self.duree_course_secondes if (self.duree_course_secondes and self.duree_course_secondes > 0) else self.duree_secondes
        if self.km_total > 0 and dur > 0:
            return round((self.km_total / dur) * 3600.0, 2)
        return None

    @computed_field
    @property
    def evolution_volume_pct(self) -> Optional[float]:
        """Évolution du volume (Km-Effort) par rapport à la semaine précédente."""
        if self.previous_week_km_effort and self.previous_week_km_effort > 0:
            diff = self.km_effort_total - self.previous_week_km_effort
            return round((diff / self.previous_week_km_effort) * 100.0, 1)
        return None

    @computed_field
    @property
    def evolution_vitesse_pct(self) -> Optional[float]:
        """Évolution de la vitesse moyenne par rapport à la semaine précédente."""
        cur_v = self.vitesse_kmh
        if cur_v and self.previous_week_vitesse_kmh and self.previous_week_vitesse_kmh > 0:
            diff = cur_v - self.previous_week_vitesse_kmh
            return round((diff / self.previous_week_vitesse_kmh) * 100.0, 1)
        return None

    @computed_field
    @property
    def evolution_rpe_pct(self) -> Optional[float]:
        """Évolution de la charge interne RPE par rapport à la semaine précédente."""
        if self.previous_week_charge_rpe and self.previous_week_charge_rpe > 0:
            diff = self.charge_rpe_totale - self.previous_week_charge_rpe
            return round((diff / self.previous_week_charge_rpe) * 100.0, 1)
        return None

    @computed_field
    @property
    def progression_generale_pct(self) -> Optional[float]:
        """Progression générale = moyenne des évolutions (Volume, Vitesse, Charge RPE)."""
        deltas = []
        if self.evolution_volume_pct is not None:
            deltas.append(self.evolution_volume_pct)
        if self.evolution_vitesse_pct is not None:
            deltas.append(self.evolution_vitesse_pct)
        if self.evolution_rpe_pct is not None:
            deltas.append(self.evolution_rpe_pct)
        if not deltas:
            return None
        return round(sum(deltas) / len(deltas), 1)

    @property
    def evolution_charge_pct(self) -> Optional[float]:
        """Alias rétrocompatible vers evolution_volume_pct."""
        return self.evolution_volume_pct

    @computed_field
    @property
    def alerte_securite(self) -> str:
        if self.progression_generale_pct is None and self.evolution_volume_pct is None:
            return "⚪ Première semaine enregistrée"
        prog = self.progression_generale_pct if self.progression_generale_pct is not None else (self.evolution_volume_pct or 0.0)
        rpe_spike = self.evolution_rpe_pct is not None and self.evolution_rpe_pct > 25.0

        if prog > 15.0 or rpe_spike:
            reasons = []
            if prog > 15.0:
                reasons.append(f"Général +{prog:.1f}%")
            if rpe_spike:
                reasons.append(f"Surcharge RPE +{self.evolution_rpe_pct:.1f}%")
            return f"🔴 Risque Blessure ({', '.join(reasons)})"
        if prog > 10.0:
            return f"🟡 Vigilance (+{prog:.1f}%)"
        return f"🟢 Progression Saine (+{prog:.1f}%)"

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
    distance_km_cible: Optional[float] = Field(None, ge=0.0)
    duree_cible_secondes: Optional[int] = Field(None, gt=0)
    allure_cible: Optional[str] = Field(None, description="Allure cible conseillée (ex: 06:30/km (+/- 15s))")
    vitesse_cible: Optional[str] = Field(None, description="Vitesse cible conseillée (ex: 9.2 km/h (+/- 0.4 km/h))")
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


class SportPlannedSessionProposal(BaseModel):
    """Proposition d'une séance dans le plan hebdomadaire proactivement conçu par le coach Otis."""
    jour: str = Field(..., description="Jour de la semaine : Lundi, Mardi, Jeudi, Samedi")
    date_seance: Optional[dt_date] = Field(None, description="Date calculée de la séance")
    type_seance: SportSessionType = Field(..., description="Type de séance")
    distance_km: Optional[float] = Field(None, description="Distance cible en km (None pour le renfo)")
    duree_minutes: int = Field(..., description="Durée cible en minutes")
    allure_cible: Optional[str] = Field(None, description="Allure cible conseillée avec marge (ex: 06:15/km (+/- 15s))")
    vitesse_cible: Optional[str] = Field(None, description="Vitesse cible conseillée avec marge (ex: 9.6 km/h (+/- 0.4 km/h))")
    programme: str = Field(..., description="Contenu technique détaillé de la séance")
    remarques_coach: Optional[str] = Field(None, description="Conseil spécifique du coach (sol souple, périostite, etc.)")


class SportWeeklyPlanProposal(BaseModel):
    """Proposition complète d'un plan d'entraînement hebdomadaire généré par Otis."""
    semaine: int
    annee: int
    est_semaine_repos: bool = False
    analyse_historique: str = Field(..., description="Diagnostic sur la charge récente, forme et alertes périostite")
    km_effort_total_prevu: float = Field(..., description="Cumul prévisionnel en km-effort")
    plafond_recommande: float = Field(..., description="Plafond conseillé (+10% max)")
    respecte_regle_10_pct: bool = True
    conseil_blessure_periostite: str = Field(..., description="Recommandations préventives périostite")
    seances: List[SportPlannedSessionProposal] = Field(..., description="Séances planifiées pour la semaine")
    avis_sur_souhaits_alexis: Optional[str] = Field(None, description="Feedback d'Otis sur ce qu'Alexis envisageait")
    spoken_summary: str = Field(..., description="Résumé oral concis et complice pour la voix d'Otis")


class DashboardScale(str, Enum):
    """Échelle temporelle du tableau de bord."""
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class MetricTrend(str, Enum):
    """Tendance d'évolution d'une métrique sportive."""
    UP = "up"
    DOWN = "down"
    STABLE = "stable"


class CoachTipLevel(str, Enum):
    """Niveau de criticité du conseil coach."""
    INFO = "info"
    VIGILANCE = "vigilance"
    ALERTE = "alerte"


class SportCoachTip(BaseModel):
    """Bulle conseil du Coach Otis pour le dashboard."""
    message: str = Field(..., description="Message de conseil concis et bienveillant")
    niveau: CoachTipLevel = CoachTipLevel.INFO
    source: str = Field(default="otis", description="'otis' (LLM) ou 'regles' (fallback déterministe)")
    fallback_reason: Optional[str] = Field(default=None, description="Raison du fallback si applicable")


class SessionMetricDelta(BaseModel):
    """Comparaison d'une métrique spécifique par rapport à la séance de référence."""
    metric: str
    current: Optional[float] = None
    previous: Optional[float] = None
    delta_pct: Optional[float] = None
    trend: MetricTrend = MetricTrend.STABLE


class SportSessionComparison(BaseModel):
    """Résultat de comparaison entre la séance courante et la précédente du même type."""
    current_session: SportSession
    previous_session: SportSession
    deltas: List[SessionMetricDelta] = Field(default_factory=list)


class PeriodTotals(BaseModel):
    """Cumuls et totaux sur une période donnée (semaine, mois, année)."""
    nb_seances: int = 0
    nb_renfo: int = 0
    nb_prevues: int = 0
    distance_km: float = 0.0
    km_effort: float = 0.0
    duree_secondes: int = 0
    charge_rpe: int = 0
    vitesse_kmh: Optional[float] = None
    allure_formatted: Optional[str] = None


class PeriodSeriesPoint(BaseModel):
    """Point de donnée dans une série temporelle (pour graphiques SVG/Canvas)."""
    label: str = Field(..., description="Libellé du point (ex: S41, oct., etc.)")
    km_effort: float = 0.0
    distance_km: float = 0.0
    duree_secondes: int = 0
    vitesse_kmh: Optional[float] = None
    charge_rpe: int = 0
    is_current: bool = False


class SportPeriodDashboard(BaseModel):
    """Données complètes du tableau de bord pour une échelle donnée."""
    scale: DashboardScale
    label: str
    start_date: dt_date
    end_date: dt_date
    totals: PeriodTotals
    series: List[PeriodSeriesPoint] = Field(default_factory=list)
    plafond_km_effort: Optional[float] = None
    alerte_securite: Optional[str] = None
    moyenne_km_effort_reference: Optional[float] = None
    ecart_moyenne_pct: Optional[float] = None


class SportTodayResponse(BaseModel):
    """Réponse de l'endpoint /api/v1/sport/today."""
    date: dt_date
    seances: List[SportSession] = Field(default_factory=list)
    comparisons: List[SportSessionComparison] = Field(default_factory=list)
    coach_tip: SportCoachTip
    daily_spotlight: Optional[str] = Field(default=None, description="Le Mot d'Otis / Annonce du jour")


# --- Gamification, Badges de Dopamine & Anecdotes Insolites (Étape 8) ---

class BadgeCategory(str, Enum):
    """Catégorie d'accomplissement pour les badges."""
    DISTANCE = "distance"
    DENIVELE = "denivele"
    MONO_SESSION = "mono_session"
    REGULARITE = "regularite"
    TEMPS = "temps"
    RECORD = "record"
    POP_CULTURE = "pop_culture"
    SECRET = "secret"
    ABSURDE = "absurde"


class SportBadge(BaseModel):
    """Badge de réussite ou d'accomplissement régulier."""
    id: str
    title: str
    description: str
    icon: str
    category: BadgeCategory
    is_unlocked: bool = False
    is_secret: bool = False
    unlocked_at: Optional[str] = None
    current_value: float = 0.0
    target_value: Optional[float] = None
    unit: Optional[str] = None
    progress_pct: int = 0
    rarity: str = "bronze"  # bronze, argent, or, diamant, mythique


class SportFunFact(BaseModel):
    """Anecdote insolite ou équivalence fun (géographique, verticale, énergétique, cosmique)."""
    id: str
    title: str
    text: str
    icon: str
    category: str  # geo, vertical, energy, cosmique, culture_g


class PersonalRecord(BaseModel):
    """Record personnel (PR) détecté sur l'historique."""
    record_type: str
    title: str
    value: float
    formatted_value: str
    date: Optional[dt_date] = None
    session_type: Optional[str] = None


class ImminentMilestone(BaseModel):
    """Palier imminent (dose de motivation pour le jour J ou la chronique matinale)."""
    badge_id: str
    title: str
    remaining: float
    unit: str
    message: str


class SportGamificationSummary(BaseModel):
    """Synthèse complète de gamification pour la PWA et la Chronique Matinale."""
    badges: List[SportBadge] = Field(default_factory=list)
    unlocked_count: int = 0
    total_badges: int = 0
    personal_records: List[PersonalRecord] = Field(default_factory=list)
    fun_facts: List[SportFunFact] = Field(default_factory=list)
    imminent_milestones: List[ImminentMilestone] = Field(default_factory=list)
    announcements: List[str] = Field(default_factory=list, description="Annonces marquantes et jalons majeurs")
    daily_spotlight: Optional[str] = Field(default=None, description="Annonce du jour d'Otis (ex: Aujourd'hui on passe le cap des 100 km !)")
    next_target_message: Optional[str] = None


# --- Modèles de réponses d'historique (Étape 2) ---

class SportSessionsListResponse(BaseModel):
    """Réponse paginée pour l'historique complet des séances de course et renforcement."""
    sessions: List[SportSession] = Field(default_factory=list, description="Liste des séances triées")
    total: int = Field(0, description="Nombre total de séances correspondant aux filtres")


class SportWeeklySummaryWithSessions(BaseModel):
    """Synthèse hebdomadaire accompagnée de ses séances détaillées."""
    summary: SportWeeklySummary = Field(..., description="Données agrégées de la semaine")
    seances: List[SportSession] = Field(default_factory=list, description="Séances composant cette semaine")


class SportSummariesListResponse(BaseModel):
    """Réponse pour l'historique des semaines d'entraînement."""
    summaries: List[SportWeeklySummaryWithSessions] = Field(default_factory=list, description="Liste des synthèses hebdomadaires")
    total: int = Field(0, description="Nombre total de semaines disponibles")
