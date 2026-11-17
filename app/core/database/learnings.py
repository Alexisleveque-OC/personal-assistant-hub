"""Règles apprises à la voix par Otis (user_learnings)."""
import sqlite3
from typing import Any, Dict, List, Optional

from app.core.database.base import SQLiteBase


class LearningsStore(SQLiteBase):
    """Table user_learnings."""

    @staticmethod
    def _create_learnings_schema(cursor: sqlite3.Cursor) -> None:
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

    def add_learning(
        self,
        rule_text: str,
        category: str = "general",
        original_error: Optional[str] = None,
        correction: Optional[str] = None,
        active: bool = True,
    ) -> int:
        """Enregistre une règle d'apprentissage extraite d'une interaction."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO user_learnings (rule_text, category, original_error, correction, active)
                VALUES (?, ?, ?, ?, ?)
                """,
                (rule_text, category, original_error, correction, 1 if active else 0),
            )
            return cursor.lastrowid

    def get_learning(self, learning_id: int) -> Optional[Dict[str, Any]]:
        """Récupère une règle d'apprentissage par son ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_learnings WHERE id = ?", (learning_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_learning_dict(row)

    def get_learnings(
        self,
        category: Optional[str] = None,
        active: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Récupère la liste filtrée et paginée des règles apprises."""
        conditions = []
        params: List[Any] = []

        if category:
            conditions.append("category = ?")
            params.append(category)
        if active is not None:
            conditions.append("active = ?")
            params.append(1 if active else 0)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM user_learnings {where_clause}", tuple(params))
            total = cursor.fetchone()[0]

            query = f"""
                SELECT * FROM user_learnings
                {where_clause}
                ORDER BY id DESC
                LIMIT ? OFFSET ?
            """
            cursor.execute(query, tuple(params + [limit, offset]))
            items = [self._row_to_learning_dict(row) for row in cursor.fetchall()]

            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "items": items,
            }

    def get_active_learnings(self) -> List[Dict[str, Any]]:
        """Récupère toutes les règles actives prêtes pour injection dans le prompt NLU."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM user_learnings WHERE active = 1 ORDER BY id ASC"
            )
            return [self._row_to_learning_dict(row) for row in cursor.fetchall()]

    def update_learning(
        self,
        learning_id: int,
        rule_text: Optional[str] = None,
        category: Optional[str] = None,
        original_error: Optional[str] = None,
        correction: Optional[str] = None,
        active: Optional[bool] = None,
    ) -> bool:
        """Met à jour une règle existante."""
        fields = []
        params: List[Any] = []

        if rule_text is not None:
            fields.append("rule_text = ?")
            params.append(rule_text)
        if category is not None:
            fields.append("category = ?")
            params.append(category)
        if original_error is not None:
            fields.append("original_error = ?")
            params.append(original_error)
        if correction is not None:
            fields.append("correction = ?")
            params.append(correction)
        if active is not None:
            fields.append("active = ?")
            params.append(1 if active else 0)

        if not fields:
            return False

        params.append(learning_id)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE user_learnings SET {', '.join(fields)} WHERE id = ?",
                tuple(params),
            )
            return cursor.rowcount > 0

    def delete_learning(self, learning_id: int) -> bool:
        """Supprime une règle d'apprentissage."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM user_learnings WHERE id = ?", (learning_id,))
            return cursor.rowcount > 0

    @staticmethod
    def _row_to_learning_dict(row: sqlite3.Row) -> Dict[str, Any]:
        """Convertit un row SQLite en dictionnaire avec cast booléen du statut actif."""
        data = dict(row)
        data["active"] = bool(data["active"])
        return data
