"""Socle de base de données unifiée SQLite pour Personal Assistant Hub.

Gère la persistance locale haute performance (< 1ms, mode WAL) :
- Journalisation conversationnelle et audit (conversation_logs)
- Feedbacks et corrections (conversation_feedbacks)
- Règles apprises à la voix (user_learnings)
- Second cerveau compartimenté (second_brain_notes)
"""
from contextlib import contextmanager
import json
import logging
import os
import sqlite3
from typing import Any, Dict, Generator, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Gestionnaire de persistance SQLite avec mode WAL et pragma haute performance."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or getattr(settings, "sqlite_db_path", "hub_data.db")
        self._ensure_parent_dir()

    def _ensure_parent_dir(self) -> None:
        """Crée le dossier parent si le chemin de la base est dans un sous-dossier."""
        if self.db_path and self.db_path != ":memory:":
            dirname = os.path.dirname(self.db_path)
            if dirname and not os.path.exists(dirname):
                os.makedirs(dirname, exist_ok=True)

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Fournit une connexion SQLite avec row_factory Row et autocommit propre."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        try:
            yield conn
            conn.commit()

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        """Initialise les pragmas (WAL, FK) et crée le schéma de tables si nécessaire."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Configuration pragmas de performance et d'intégrité
            cursor.execute("PRAGMA journal_mode = WAL;")
            cursor.execute("PRAGMA synchronous = NORMAL;")
            cursor.execute("PRAGMA foreign_keys = ON;")
            cursor.execute("PRAGMA busy_timeout = 5000;")

            # 1. Journal Conversationnel (conversation_logs)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    raw_query TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    parameters TEXT DEFAULT '{}',
                    spoken_response TEXT NOT NULL,
                    success INTEGER NOT NULL DEFAULT 1,
                    latency_ms REAL DEFAULT 0.0,
                    llm_model TEXT,
                    error_trace TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_conv_logs_created_at ON conversation_logs(created_at DESC);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_conv_logs_session_id ON conversation_logs(session_id);"
            )

            # 2. Retours & Feedbacks (conversation_feedbacks)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_feedbacks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    log_id INTEGER NOT NULL REFERENCES conversation_logs(id) ON DELETE CASCADE,
                    feedback_type TEXT NOT NULL,
                    user_note TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_conv_feedbacks_log_id ON conversation_feedbacks(log_id);"
            )

            # 3. Règles apprises par Otis (user_learnings)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_learnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_text TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    original_error TEXT,
                    correction TEXT,
                    active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_learnings_active ON user_learnings(active);"
            )

            # 4. Second Cerveau compartimenté (second_brain_notes)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS second_brain_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_second_brain_category ON second_brain_notes(category);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_second_brain_status ON second_brain_notes(status);"
            )

        logger.info(f"Base de données SQLite initialisée avec succès : {self.db_path} (mode WAL)")

    def log_conversation(
        self,
        raw_query: str,
        intent: str,
        spoken_response: str,
        session_id: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        success: bool = True,
        latency_ms: float = 0.0,
        llm_model: Optional[str] = None,
        error_trace: Optional[str] = None,
    ) -> int:
        """Enregistre une interaction conversationnelle dans la base."""
        param_json = json.dumps(parameters or {}, ensure_ascii=False)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO conversation_logs (
                    session_id, raw_query, intent, parameters,
                    spoken_response, success, latency_ms, llm_model, error_trace
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    raw_query,
                    intent,
                    param_json,
                    spoken_response,
                    1 if success else 0,
                    latency_ms,
                    llm_model,
                    error_trace,
                ),
            )
            return cursor.lastrowid

    def get_conversation_log(self, log_id: int) -> Optional[Dict[str, Any]]:
        """Récupère un enregistrement précis du journal par son ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM conversation_logs WHERE id = ?", (log_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_log_dict(row)

    def get_conversation_logs(
        self,
        limit: int = 50,
        offset: int = 0,
        session_id: Optional[str] = None,
        success: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Récupère la liste paginée des échanges conversationnels avec filtres."""
        conditions = []
        params: List[Any] = []

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if success is not None:
            conditions.append("success = ?")
            params.append(1 if success else 0)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Nombre total
            cursor.execute(f"SELECT COUNT(*) FROM conversation_logs {where_clause}", tuple(params))
            total = cursor.fetchone()[0]

            # Éléments paginés triés antichronologiquement
            query = f"""
                SELECT * FROM conversation_logs
                {where_clause}
                ORDER BY id DESC
                LIMIT ? OFFSET ?
            """
            cursor.execute(query, tuple(params + [limit, offset]))
            items = [self._row_to_log_dict(row) for row in cursor.fetchall()]

            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "items": items,
            }

    def add_feedback(
        self,
        log_id: int,
        feedback_type: str,
        user_note: Optional[str] = None,
    ) -> int:
        """Enregistre un feedback ou signalement d'erreur utilisateur."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO conversation_feedbacks (log_id, feedback_type, user_note)
                VALUES (?, ?, ?)
                """,
                (log_id, feedback_type, user_note),
            )
            return cursor.lastrowid

    def get_feedbacks_for_log(self, log_id: int) -> List[Dict[str, Any]]:
        """Récupère tous les feedbacks associés à un log."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM conversation_feedbacks WHERE log_id = ? ORDER BY id ASC",
                (log_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def _row_to_log_dict(row: sqlite3.Row) -> Dict[str, Any]:
        """Convertit un row SQLite en dictionnaire avec parsing du JSON de paramètres."""
        data = dict(row)
        data["success"] = bool(data["success"])
        if isinstance(data.get("parameters"), str):
            try:
                data["parameters"] = json.loads(data["parameters"])
            except Exception:
                data["parameters"] = {}
        return data


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
