"""Journal de conversation : échanges, retours (feedbacks) et lots d'annulation de l'agent."""
import json
import sqlite3
from typing import Any, Dict, List, Optional

from app.core.database.base import SQLiteBase


class ConversationStore(SQLiteBase):
    """Tables conversation_logs, conversation_feedbacks et agent_undo_batches."""

    @staticmethod
    def _create_conversation_schema(cursor: sqlite3.Cursor) -> None:
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

        # 7. Journal d'annulation de l'agent (instantanés par tour, persistés malgré les redémarrages)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_undo_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                undos_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                undone_at TIMESTAMP
            );
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_undo_session ON agent_undo_batches(session_id, id DESC);"
        )

    def add_agent_undo_batch(self, session_id: str, undos_json: str) -> int:
        """Enregistre le lot d'instantanés d'un tour de l'agent."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO agent_undo_batches (session_id, undos_json) VALUES (?, ?)",
                (session_id, undos_json),
            )
            return cursor.lastrowid

    def get_last_agent_undo_batch(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Récupère le dernier lot non encore annulé d'une session."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM agent_undo_batches WHERE session_id = ? AND undone_at IS NULL ORDER BY id DESC LIMIT 1",
                (session_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def mark_agent_undo_batch_undone(self, batch_id: int) -> bool:
        """Marque un lot comme annulé (il ne sera plus proposé)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE agent_undo_batches SET undone_at = CURRENT_TIMESTAMP WHERE id = ? AND undone_at IS NULL",
                (batch_id,),
            )
            return cursor.rowcount > 0

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
        param_json = json.dumps(parameters or {}, ensure_ascii=False, default=str)
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
