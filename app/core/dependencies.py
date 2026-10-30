"""Centralisation des dépendances et singletons pour les connecteurs et sessions.

Élimine définitivement les dépendances circulaires entre main.py et les routers.
Fournit des factories injectables pour FastAPI (Depends) et les tests unitaires.
"""
from typing import Any, Dict, Optional
import logging

from app.config import settings
from app.connectors.calendar.calendar_connector import CalendarConnector
from app.connectors.google_oauth import GoogleOAuthNotConfiguredError
from app.connectors.sheets.meals_connector import MealsShoppingConnector
from app.connectors.sheets.sport_connector import SportConnector
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.database import (
    DatabaseManager,
    get_database_manager,
    set_database_manager,
)

logger = logging.getLogger(__name__)

_meals_connector: Any = "UNSET"
_sport_connector: Any = "UNSET"
_sport_connector_error: Optional[str] = None
_calendar_connector: Any = "UNSET"
_calendar_connector_error: str = ""
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


def get_calendar_connector() -> Optional[CalendarConnector]:
    """Récupère le connecteur Agenda (OAuth utilisateur) ou tente son initialisation ; cause d'échec conservée."""
    global _calendar_connector, _calendar_connector_error
    if _calendar_connector == "UNSET":
        try:
            _calendar_connector = CalendarConnector.from_settings(settings)
            _calendar_connector_error = ""
        except GoogleOAuthNotConfiguredError as exc:
            logger.warning(f"Agenda Google non configuré : {exc}")
            _calendar_connector = None
            _calendar_connector_error = str(exc)
    return _calendar_connector


def get_calendar_connector_error() -> str:
    return _calendar_connector_error


def set_calendar_connector(connector: Optional[Any], error: str = "") -> None:
    """Permet l'injection d'un connecteur Agenda (doublure) ou son absence motivée, pour les tests."""
    global _calendar_connector, _calendar_connector_error
    _calendar_connector = connector
    _calendar_connector_error = error


def get_sport_connector_error() -> Optional[str]:
    """Retourne la dernière erreur d'initialisation du connecteur sport."""
    return _sport_connector_error


def get_sport_connector() -> Optional[Any]:
    """Récupère l'instance active du connecteur sport (SqlSportConnector par défaut) ou tente son initialisation."""
    global _sport_connector, _sport_connector_error
    if _sport_connector == "UNSET":
        try:
            _sport_connector = SqlSportConnector()
            _sport_connector_error = None
        except Exception as exc:
            logger.warning(f"Impossible d'initialiser SqlSportConnector : {exc}")
            _sport_connector = None
            _sport_connector_error = str(exc)
    return _sport_connector


def set_sport_connector(connector: Optional[Any]) -> None:
    """Permet l'injection d'un connecteur sport (mock) pour les tests unitaires et d'intégration."""
    global _sport_connector, _sport_connector_error
    _sport_connector = connector
    if connector is None:
        _sport_connector_error = "Connecteur non initialisé ou mock désactivé"


def get_sessions_store() -> Dict[str, Dict[str, Any]]:
    """Retourne le dictionnaire de mémoire des sessions multi-tours."""
    from app.core.session_manager import get_session_manager
    return get_session_manager().as_dict_store()


def clear_sessions() -> None:
    """Réinitialise la mémoire de session (utilitaire pour les tests)."""
    from app.core.session_manager import get_session_manager
    get_session_manager().clear_all()

