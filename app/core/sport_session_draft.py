"""« Dicte ta séance » (refonte UX, décision du 10/11) : la dictée devient un brouillon de séance, sans rien enregistrer.

Un seul appel Gemini en sortie JSON structurée extrait les champs dits ; chaque champ est validé séparément pour
qu'une valeur aberrante (RPE 12, type retiré…) laisse le champ vide au lieu de faire échouer tout le brouillon.
Le formulaire Séance affiche ensuite les champs : l'utilisateur corrige et c'est « OK » qui enregistre."""
import json
import logging
import time
from datetime import date, date as dt_date, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.connectors.sheets.sport_models import ProposedSessionType, SportSessionStatus
from app.core.clock import paris_today
from app.core.llm.gemini_client import GEMINI_API_BASE_URL, get_gemini_client

logger = logging.getLogger(__name__)

WEEKDAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


class SessionDraftUnavailableError(RuntimeError):
    """Gemini n'a pas pu produire de brouillon (réseau, quotas, réponse illisible)."""


class SessionDraft(BaseModel):
    """Champs du formulaire Séance ; vide = non dit."""
    date: Optional[dt_date] = None
    statut: Optional[SportSessionStatus] = None
    type_seance: Optional[ProposedSessionType] = None
    distance_km: Optional[float] = Field(None, ge=0.0, le=300.0)
    duree_secondes: Optional[int] = Field(None, ge=0, le=24 * 3600)
    denivele_d_plus: Optional[int] = Field(None, ge=0, le=10000)
    ressenti_rpe: Optional[int] = Field(None, ge=1, le=10)
    meteo_note: Optional[int] = Field(None, ge=1, le=10)
    fc_moyenne: Optional[int] = Field(None, ge=30, le=250)
    fc_max: Optional[int] = Field(None, ge=30, le=250)
    douleur_intensite: Optional[int] = Field(None, ge=0, le=10)
    douleur_zone: Optional[str] = Field(None, max_length=60)
    remarques: Optional[str] = None

    model_config = {"use_enum_values": True}


class SessionDraftResult(BaseModel):
    draft: SessionDraft
    dropped: List[str] = Field(default_factory=list, description="Champs proposés par Gemini mais invalides")


DRAFT_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "date": {"type": "STRING", "description": "AAAA-MM-JJ"},
        "statut": {"type": "STRING", "enum": [s.value for s in (SportSessionStatus.REALISE, SportSessionStatus.PLANIFIE)]},
        "type_seance": {"type": "STRING", "enum": [t.value for t in ProposedSessionType]},
        "distance_km": {"type": "NUMBER"},
        "duree_secondes": {"type": "INTEGER"},
        "denivele_d_plus": {"type": "INTEGER"},
        "ressenti_rpe": {"type": "INTEGER"},
        "meteo_note": {"type": "INTEGER"},
        "fc_moyenne": {"type": "INTEGER"},
        "fc_max": {"type": "INTEGER"},
        "douleur_intensite": {"type": "INTEGER"},
        "douleur_zone": {"type": "STRING"},
        "remarques": {"type": "STRING"},
    },
}


def build_draft_prompt(text: str, today: date) -> str:
    yesterday = today - timedelta(days=1)
    return (
        "Tu remplis le formulaire d'une séance de sport à partir de ce que l'utilisateur a dicté (en français).\n"
        f"Aujourd'hui : {WEEKDAYS_FR[today.weekday()]} {today.strftime('%d/%m/%Y')} ; "
        f"hier : {WEEKDAYS_FR[yesterday.weekday()]} {yesterday.strftime('%d/%m/%Y')}.\n"
        "Règles :\n"
        "- N'invente rien : un champ qui n'est pas dit reste absent.\n"
        "- date au format AAAA-MM-JJ (« hier », « lundi » = le plus récent passé, sauf séance prévue) ; "
        "statut « Prévu » seulement pour une séance future, sinon « Réalisé ».\n"
        "- type_seance : EF pour un footing d'endurance tranquille, Sortie Longue, Vitesse, Fractionné, "
        "Renforcement (renfo, PPG, muscu), sinon Course.\n"
        "- duree_secondes en secondes (« 45 minutes 57 » = 2757) ; distance_km en km ; denivele_d_plus en mètres.\n"
        "- ressenti_rpe (effort) de 1 à 10.\n"
        "- meteo_note = DIFFICULTÉ due à la météo, de 1 (conditions idéales) à 10 (très pénible) : beau temps doux "
        "≈ 2, chaleur, vent ou pluie forte ≈ 7 ; absente si la météo n'est pas évoquée.\n"
        "- douleur_intensite de 0 à 10 et douleur_zone (ex. « genou droit ») seulement si une douleur est dite.\n"
        "- remarques : les sensations dites, reformulées proprement en une ou deux phrases.\n\n"
        f"Dictée : « {text} »"
    )


def parse_draft(raw: Dict[str, Any]) -> Tuple[SessionDraft, List[str]]:
    """Valide champ par champ : les valeurs invalides sont écartées (et listées), le reste est gardé."""
    kept: Dict[str, Any] = {}
    dropped: List[str] = []
    for key, value in (raw or {}).items():
        if key not in SessionDraft.model_fields or value is None or value == "":
            continue
        try:
            SessionDraft.model_validate({key: value})
        except ValidationError:
            dropped.append(key)
            continue
        kept[key] = value
    return SessionDraft.model_validate(kept), dropped


# Sortie structurée plus lente qu'une réponse libre ; le formulaire attend, sans bloquer le reste de l'app.
DRAFT_TIMEOUT_SECONDS = 20.0

LLMCaller = Callable[[str, Dict[str, Any]], Awaitable[Dict[str, Any]]]


async def _call_gemini_json(prompt: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """Appel Gemini en sortie JSON structurée, avec repli sur les modèles candidats (comme le coach hebdo)."""
    client = get_gemini_client()
    if not client.is_configured:
        raise SessionDraftUnavailableError("Clé Gemini absente : brouillon impossible.")
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "response_mime_type": "application/json", "response_schema": schema},
    }
    failures: List[str] = []
    await client.resolve_model()  # remplit la liste des candidats (modèle actif en tête)
    for candidate in client.get_candidate_models():
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=DRAFT_TIMEOUT_SECONDS) as http_client:
                response = await http_client.post(
                    f"{GEMINI_API_BASE_URL}/models/{candidate}:generateContent",
                    headers={"x-goog-api-key": client.api_key}, json=payload,
                )
            if response.status_code == 429:
                client.mark_model_temporarily_unavailable(candidate, 60.0)
            if response.status_code in (429, 503, 404):
                failures.append(f"{candidate} : HTTP {response.status_code}")
                continue
            response.raise_for_status()
            client.record_request((time.perf_counter() - start) * 1000)
            text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise ValueError(f"objet JSON attendu, reçu {type(parsed).__name__}")
            return parsed
        except Exception as exc:  # noqa: BLE001 — on passe au modèle suivant, la cause est gardée
            failures.append(f"{candidate} : {type(exc).__name__} {exc}")
            logger.warning(f"Brouillon de séance : échec sur {candidate} : {exc}")
    raise SessionDraftUnavailableError("Aucun modèle Gemini n'a produit de brouillon (" + " ; ".join(failures) + ").")


class SessionDraftService:
    def __init__(self, llm_caller: Optional[LLMCaller] = None, today: Callable[[], date] = paris_today) -> None:
        self.llm_caller = llm_caller or _call_gemini_json
        self.today = today

    async def draft(self, text: str) -> SessionDraftResult:
        raw = await self.llm_caller(build_draft_prompt(text, self.today()), DRAFT_SCHEMA)
        draft, dropped = parse_draft(raw)
        if dropped:
            logger.warning(f"Brouillon de séance : champs écartés (invalides) : {dropped} — proposés : {raw}")
        return SessionDraftResult(draft=draft, dropped=dropped)


_service: Optional[SessionDraftService] = None


def get_session_draft_service() -> SessionDraftService:
    global _service
    if _service is None:
        _service = SessionDraftService()
    return _service


def set_session_draft_service(service: Optional[Any]) -> None:
    """Injection d'un service (doublure) pour les tests."""
    global _service
    _service = service
