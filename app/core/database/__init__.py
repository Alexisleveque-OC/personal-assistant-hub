"""Socle de base de données unifiée SQLite pour Personal Assistant Hub.

Gère la persistance locale haute performance (< 1ms, mode WAL) :
- Journalisation conversationnelle et audit (conversation_logs)
- Feedbacks et corrections (conversation_feedbacks)
- Règles apprises à la voix (user_learnings)
- Second cerveau compartimenté (second_brain_notes)
- Séances de sport et synthèses hebdomadaires (sport_sessions, sport_weekly_summaries)
- Lots d'annulation de l'agent (agent_undo_batches)
- Consommation de l'API payante Claude (llm_usage)

Un module par domaine (conversation, notes, learnings, sport, llm_usage), assemblés ici dans DatabaseManager.
"""
import logging
from typing import Optional

from app.core.database.conversation import ConversationStore
from app.core.database.learnings import LearningsStore
from app.core.database.llm_usage import LlmUsageStore
from app.core.database.notes import NotesStore
from app.core.database.sport import SportStore

logger = logging.getLogger(__name__)


class DatabaseManager(ConversationStore, LearningsStore, NotesStore, SportStore, LlmUsageStore):
    """Gestionnaire de persistance SQLite avec mode WAL et pragma haute performance."""

    def init_db(self) -> None:
        """Initialise les pragmas (WAL, FK) et crée le schéma de tables si nécessaire."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Configuration pragmas de performance et d'intégrité
            cursor.execute("PRAGMA journal_mode = WAL;")
            cursor.execute("PRAGMA synchronous = NORMAL;")
            cursor.execute("PRAGMA foreign_keys = ON;")
            cursor.execute("PRAGMA busy_timeout = 5000;")

            self._create_conversation_schema(cursor)
            self._create_learnings_schema(cursor)
            self._create_notes_schema(cursor)
            self._create_sport_schema(cursor)
            self._create_llm_usage_schema(cursor)

        logger.info(f"Base de données SQLite initialisée avec succès : {self.db_path} (mode WAL)")


_db_manager: Optional[DatabaseManager] = None


def get_database_manager() -> DatabaseManager:
    """Fournit l'instance globale du DatabaseManager (Singleton)."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def set_database_manager(manager: Optional[DatabaseManager]) -> None:
    """Permet l'injection d'un DatabaseManager (mock ou base de test temporaire)."""
    global _db_manager
    _db_manager = manager
