"""Client HTTP asynchrone pour l'API Google Gemini avec auto-découverte dynamique du modèle et garde-fou de quotas."""
from datetime import date
import logging
import re
from typing import Any, Dict, List, Optional
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_FALLBACK_MODEL = "gemini-3.6-flash"
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


def _parse_gemini_version(model_name: str) -> tuple[int, ...]:
    """Extrait le tuple de version majeure/mineure d'un nom de modèle Gemini (ex: 'gemini-3.6-flash' -> (3, 6))."""
    match = re.search(r"gemini-(\d+)(?:\.(\d+))?", model_name.lower())
    if match:
        major = int(match.group(1))
        minor = int(match.group(2) or 0)
        return (major, minor)
    return (0, 0)


class GeminiClient:
    """Client pour interagir avec l'API Google Gemini, sélectionner le modèle optimal et surveiller les quotas."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 10.0,
        max_daily_requests: Optional[int] = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.configured_model = model or settings.gemini_model or "auto"
        self.timeout = timeout
        self.max_daily_requests = (
            max_daily_requests
            if max_daily_requests is not None
            else getattr(settings, "gemini_max_daily_requests", 1000)
        )
        self._resolved_model: Optional[str] = None
        self._candidate_models: List[str] = []

        # Suivi pédagogique des métriques & quotas
        self._daily_requests_count: int = 0
        self._last_reset_date: date = date.today()
        self._total_requests_count: int = 0
        self._last_latency_ms: float = 0.0

    @property
    def is_configured(self) -> bool:
        """Indique si une clé API est configurée."""
        return bool(self.api_key and self.api_key.strip())

    def _check_and_reset_daily(self) -> None:
        """Réinitialise automatiquement le compteur si la date du jour a changé."""
        today = date.today()
        if today != self._last_reset_date:
            self._daily_requests_count = 0
            self._last_reset_date = today

    def is_daily_quota_exceeded(self) -> bool:
        """Indique si le garde-fou de sécurité du nombre de requêtes journalières est atteint."""
        self._check_and_reset_daily()
        return self._daily_requests_count >= self.max_daily_requests

    def record_request(self, latency_ms: float = 0.0) -> None:
        """Enregistre une requête exécutée avec succès pour le suivi des métriques."""
        self._check_and_reset_daily()
        self._daily_requests_count += 1
        self._total_requests_count += 1
        self._last_latency_ms = round(latency_ms, 2)

    def get_usage_stats(self) -> Dict[str, Any]:
        """Retourne le bilan d'utilisation et des quotas pour affichage dans la PWA."""
        self._check_and_reset_daily()
        remaining = max(0, self.max_daily_requests - self._daily_requests_count)
        return {
            "model": self._resolved_model or self.configured_model,
            "configured_model": self.configured_model,
            "is_configured": self.is_configured,
            "daily_requests": self._daily_requests_count,
            "max_daily_requests": self.max_daily_requests,
            "remaining_daily_requests": remaining,
            "total_requests": self._total_requests_count,
            "last_latency_ms": self._last_latency_ms,
            "quota_exceeded": self.is_daily_quota_exceeded(),
        }

    async def resolve_model(self, force_refresh: bool = False) -> str:
        """Résout le modèle à utiliser.
        
        - Si un modèle explicite est configuré (différent de 'auto'), il est utilisé directement.
        - Si 'auto', interroge l'API pour sélectionner la version stable la plus récente de la famille Flash.
        - Met en cache le résultat en mémoire.
        - Retombe gracieusement sur DEFAULT_FALLBACK_MODEL en cas d'erreur ou d'absence de clé.
        """
        # 1. Modèle explicite fixé par l'utilisateur
        if self.configured_model and self.configured_model.lower() != "auto":
            return self.configured_model

        # 2. Utilisation du cache mémoire
        if self._resolved_model and not force_refresh:
            return self._resolved_model

        # 3. Absence de clé d'API -> Repli immédiat
        if not self.is_configured:
            logger.info(
                f"Aucune clé GEMINI_API_KEY configurée. Utilisation du modèle de repli : {DEFAULT_FALLBACK_MODEL}"
            )
            self._resolved_model = DEFAULT_FALLBACK_MODEL
            return self._resolved_model

        # 4. Auto-découverte via l'API Google
        try:
            url = f"{GEMINI_API_BASE_URL}/models?key={self.api_key}"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()

            models: List[Dict[str, Any]] = data.get("models", [])
            selected = self._select_best_flash_model(models)
            self._resolved_model = selected
            logger.info(f"Modèle Gemini résolu dynamiquement : {self._resolved_model}")
            return self._resolved_model

        except Exception as exc:
            logger.warning(
                f"Échec de l'auto-découverte du modèle Gemini ({exc}). "
                f"Bascule sur le modèle de repli : {DEFAULT_FALLBACK_MODEL}"
            )
            self._resolved_model = DEFAULT_FALLBACK_MODEL
            return self._resolved_model

    def _select_best_flash_model(self, models: List[Dict[str, Any]]) -> str:
        """Sélectionne le modèle Flash le plus récent parmi les modèles disponibles."""
        stable_flash_candidates: List[str] = []
        any_flash_candidates: List[str] = []

        unstable_keywords = ("thinking", "exp", "experimental", "preview")

        for m in models:
            raw_name = m.get("name", "")
            methods = m.get("supportedGenerationMethods", [])

            if "generateContent" not in methods:
                continue

            clean_name = raw_name.replace("models/", "").strip()
            name_lower = clean_name.lower()

            if "flash" in name_lower:
                any_flash_candidates.append(clean_name)
                if not any(kw in name_lower for kw in unstable_keywords):
                    stable_flash_candidates.append(clean_name)

        # On privilégie les modèles stables
        candidates = stable_flash_candidates or any_flash_candidates

        if not candidates:
            return DEFAULT_FALLBACK_MODEL

        # Tri par version décroissante (ex: (3, 8) > (3, 6))
        candidates.sort(key=_parse_gemini_version, reverse=True)
        self._candidate_models = candidates
        return candidates[0]

    def get_candidate_models(self) -> List[str]:
        """Retourne la liste des modèles candidats par ordre de priorité pour le basculement."""
        if self._candidate_models:
            return list(self._candidate_models)
        if self.configured_model and self.configured_model.lower() != "auto":
            return [self.configured_model]
        return [self._resolved_model or DEFAULT_FALLBACK_MODEL]

    def set_resolved_model(self, model: str) -> None:
        """Met à jour le modèle résolu actif."""
        self._resolved_model = model


_gemini_client: Optional[GeminiClient] = None


def get_gemini_client() -> GeminiClient:
    """Fournit l'instance globale du client Gemini (Singleton)."""
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = GeminiClient()
    return _gemini_client


def set_gemini_client(client: Optional[GeminiClient]) -> None:
    """Permet d'injecter un client (mock) pour les tests."""
    global _gemini_client
    _gemini_client = client
