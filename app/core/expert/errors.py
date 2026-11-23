"""Erreurs explicites de l'expert Claude. Comme celles de l'agent, elles transportent les outils déjà exécutés,
et en plus la consommation (tokens) des appels déjà facturés."""
from typing import Any, List

from app.core.agent.errors import AgentError


class ExpertError(AgentError):
    def __init__(self, message: str, *args: Any, **kwargs: Any) -> None:
        super().__init__(message, *args, **kwargs)
        self.usages: List[Any] = []  # `ExpertUsage` des appels facturés avant l'échec


class ExpertUnavailableError(ExpertError):
    """Claude injoignable : clé absente ou refusée, crédit épuisé, débit limité, panne ou réseau."""


class ExpertLLMError(ExpertError):
    """Requête refusée par l'API Claude (ex. HTTP 400) : bug de format à corriger, pas de nouvel essai."""


class ExpertResponseError(ExpertError):
    """Réponse inexploitable de Claude (ex. texte vide)."""


class ExpertRefusalError(ExpertError):
    """Claude a refusé de répondre (stop_reason « refusal »), même après le modèle de repli."""


class ExpertLoopLimitError(ExpertError):
    """Nombre maximal d'appels Claude atteint sans réponse finale."""
