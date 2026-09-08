"""Classe de base abstraite pour tous les connecteurs externes."""
from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseConnector(ABC):
    """Interface standardisée pour tous les connecteurs (Sheets, Tasks, Gmail, Domotique)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Nom identifiant le connecteur."""
        pass

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Vérifie si le service distant est accessible."""
        pass

    @abstractmethod
    async def execute_action(self, action_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Exécute une action spécifique sur le service."""
        pass
