"""Centralisation des dépendances et singletons pour les connecteurs et sessions.

Élimine définitivement les dépendances circulaires entre main.py et les routers.
Fournit des factories injectables pour FastAPI (Depends) et les tests unitaires.
"""
from typing import Any, Dict, Optional
import logging

from app.config import settings
from app.connectors.calendar.calendar_connector import CalendarConnector
from app.connectors.calendar.task_events import TaskEventsConnector
from app.connectors.google_oauth import GoogleOAuthNotConfiguredError
from app.connectors.sheets.budget_connector import BudgetConnector
from app.connectors.sheets.meals_connector import MealsShoppingConnector
from app.connectors.sheets.sport_connector import SportConnector
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.connectors.tasks.tasks_connector import TasksConnector
from app.core.database import (
    DatabaseManager,
    get_database_manager,
    set_database_manager,
)

logger = logging.getLogger(__name__)

_meals_connector: Any = "UNSET"
_budget_connector: Any = "UNSET"
_budget_connector_error: str = ""
_sport_connector: Any = "UNSET"
_sport_connector_error: Optional[str] = None
_calendar_connector: Any = "UNSET"
_calendar_connector_error: str = ""
_tasks_connector: Any = "UNSET"
_tasks_connector_error: str = ""
_task_events_connector: Any = "UNSET"
_task_events_connector_error: str = ""
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


def get_budget_connector() -> Optional[BudgetConnector]:
    """Classeur Budget (compte de service) ou tentative d'ouverture ; cause d'échec conservée pour l'utilisateur."""
    global _budget_connector, _budget_connector_error
    if _budget_connector == "UNSET":
        try:
            _budget_connector = BudgetConnector.from_settings(settings)
            _budget_connector_error = ""
        except Exception as exc:  # identifiant absent, partage manquant, réseau : dit à l'utilisateur, pas masqué
            logger.warning(f"Classeur Budget indisponible : {exc}")
            _budget_connector = None
            _budget_connector_error = str(exc) or type(exc).__name__
    return _budget_connector


def get_budget_connector_error() -> str:
    return _budget_connector_error


def set_budget_connector(connector: Optional[Any], error: str = "") -> None:
    """Permet l'injection d'un connecteur Budget (doublure) ou son absence motivée, pour les tests."""
    global _budget_connector, _budget_connector_error
    _budget_connector = connector
    _budget_connector_error = error


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


def get_tasks_connector() -> Optional[TasksConnector]:
    """Récupère le connecteur Google Tasks (OAuth utilisateur) ou tente son initialisation ; cause d'échec conservée."""
    global _tasks_connector, _tasks_connector_error
    if _tasks_connector == "UNSET":
        try:
            _tasks_connector = TasksConnector.from_settings(settings)
            _tasks_connector_error = ""
        except GoogleOAuthNotConfiguredError as exc:
            logger.warning(f"Google Tasks non configuré : {exc}")
            _tasks_connector = None
            _tasks_connector_error = str(exc)
    return _tasks_connector


def get_tasks_connector_error() -> str:
    return _tasks_connector_error


def set_tasks_connector(connector: Optional[Any], error: str = "") -> None:
    """Permet l'injection d'un connecteur Tasks (doublure) ou son absence motivée, pour les tests."""
    global _tasks_connector, _tasks_connector_error
    _tasks_connector = connector
    _tasks_connector_error = error


def get_task_events_connector() -> Optional[TaskEventsConnector]:
    """Événements Agenda des tâches avec heure (OAuth utilisateur, droit calendar.events) ; cause d'échec conservée."""
    global _task_events_connector, _task_events_connector_error
    if _task_events_connector == "UNSET":
        try:
            _task_events_connector = TaskEventsConnector.from_settings(settings)
            _task_events_connector_error = ""
        except GoogleOAuthNotConfiguredError as exc:
            logger.warning(f"Agenda des tâches non configuré : {exc}")
            _task_events_connector = None
            _task_events_connector_error = str(exc)
    return _task_events_connector


def get_task_events_connector_error() -> str:
    return _task_events_connector_error


def set_task_events_connector(connector: Optional[Any], error: str = "") -> None:
    """Permet l'injection d'une doublure des événements de tâches ou son absence motivée, pour les tests."""
    global _task_events_connector, _task_events_connector_error
    _task_events_connector = connector
    _task_events_connector_error = error


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

