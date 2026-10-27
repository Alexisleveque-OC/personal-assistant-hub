"""Erreurs explicites de l'agent. Chacune transporte les outils déjà exécutés (mutations comprises)
pour que l'appelant puisse les signaler ou les annuler : jamais de mutation passée sous silence."""
from typing import Any, List, Optional

from app.core.agent.tool_registry import ToolExecution


class AgentError(Exception):
    def __init__(self, message: str, executions: Optional[List[ToolExecution]] = None) -> None:
        super().__init__(message)
        self.executions: List[ToolExecution] = list(executions or [])
        self.llm_calls: List[Any] = []  # `LLMCall` mesurés avant l'échec, renseignés par la boucle agent


class AgentUnavailableError(AgentError):
    """Gemini injoignable : clé absente, quota atteint, modèles indisponibles ou réseau."""


class AgentLLMError(AgentError):
    """Requête refusée par Gemini (ex. HTTP 400) : bug de format à corriger, pas de nouvel essai."""


class AgentResponseError(AgentError):
    """Réponse inexploitable : aucun candidat, appel de fonction mal formé, texte vide."""


class AgentLoopLimitError(AgentError):
    """Nombre maximal d'appels Gemini atteint sans réponse finale."""
