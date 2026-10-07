"""Centralisation des dépendances et singletons pour les connecteurs et sessions.

Élimine définitivement les dépendances circulaires entre main.py et les routers.
Fournit des factories injectables pour FastAPI (Depends) et les tests unitaires.
"""
from typing import Any, Dict, Optional
import logging

from app.config import settings
from app.connectors.sheets.meals_connector import MealsShoppingConnector
from app.connectors.sheets.sport_connector import SportConnector

logger = logging.getLogger(__name__)

_meals_connector: Any = "UNSET"
_sport_connector: Any = "UNSET"
_sport_connector_error: Optional[str] = None
_SESSIONS: Dict[str, Dict[str, Any]] = {}


def get_meals_connector() -> Optional[MealsShoppingConnector]:
    """Récupère l'instance active du connecteur de repas ou tente son initialisation."""
    global _meals_connector
    if _meals_connector == "UNSET":
        try:
            _meals_connector = MealsShoppingConnector()
        except Exception as exc:
            logger.warning(f"Impossible d'initialiser MealsShoppingConnector : {exc}")
            _meals_connector = None
    return _meals_connector


def set_meals_connector(connector: Optional[MealsShoppingConnector]) -> None:
    """Permet l'injection d'un connecteur (mock) pour les tests unitaires et d'intégration."""
    global _meals_connector
    _meals_connector = connector


def get_sport_connector_error() -> Optional[str]:
    """Retourne la dernière erreur d'initialisation du connecteur sport."""
    return _sport_connector_error


def get_sport_connector() -> Optional[SportConnector]:
    """Récupère l'instance active du connecteur sport running ou tente son initialisation."""
    global _sport_connector, _sport_connector_error
    if _sport_connector == "UNSET":
        try:
            if not getattr(settings, "spreadsheet_sport_id", None) or not settings.spreadsheet_sport_id.strip():
                raise ValueError("Variable d'environnement SPREADSHEET_SPORT_ID manquante ou non configurée.")
            _sport_connector = SportConnector()
            _sport_connector_error = None
        except Exception as exc:
            logger.warning(f"Impossible d'initialiser SportConnector : {exc}")
            _sport_connector = None
            _sport_connector_error = str(exc)
    return _sport_connector


def set_sport_connector(connector: Optional[SportConnector]) -> None:
    """Permet l'injection d'un connecteur sport (mock) pour les tests unitaires et d'intégration."""
    global _sport_connector, _sport_connector_error
    _sport_connector = connector
    if connector is None:
        _sport_connector_error = "Connecteur non initialisé ou mock désactivé"


def get_sessions_store() -> Dict[str, Dict[str, Any]]:
    """Retourne le dictionnaire de mémoire des sessions multi-tours."""
    return _SESSIONS


def clear_sessions() -> None:
    """Réinitialise la mémoire de session (utilitaire pour les tests)."""
    _SESSIONS.clear()
