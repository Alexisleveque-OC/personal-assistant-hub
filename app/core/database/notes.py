"""Second cerveau compartimenté (second_brain_notes)."""
import json
import sqlite3
from typing import Any, Dict, List, Optional

from app.core.database.base import SQLiteBase


class NotesStore(SQLiteBase):
    """Table second_brain_notes."""

    @staticmethod
    def _create_notes_schema(cursor: sqlite3.Cursor) -> None:
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

    def add_note(
        self,
        category: str,
        content: str,
        tags: Optional[List[str]] = None,
        status: str = "active",
        created_at: Optional[str] = None,
    ) -> int:
        """Ajoute une note dans le second cerveau ; `created_at` (UTC, « AAAA-MM-JJ HH:MM:SS ») : restauration d'une note."""
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO second_brain_notes (category, content, tags, status, created_at)
                VALUES (?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
                """,
                (category, content, tags_json, status, created_at),
            )
            return cursor.lastrowid

    def get_note(self, note_id: int) -> Optional[Dict[str, Any]]:
        """Récupère une note par son identifiant unique."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM second_brain_notes WHERE id = ?", (note_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_note_dict(row)

    def get_notes(
        self,
        category: Optional[str] = None,
        status: Optional[str] = "active",
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Récupère la liste filtrée et paginée des notes."""
        conditions = []
        params: List[Any] = []

        if category:
            conditions.append("category = ?")
            params.append(category)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if search:
            conditions.append("(content LIKE ? OR tags LIKE ?)")
            params.append(f"%{search}%")
            params.append(f"%{search}%")

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM second_brain_notes {where_clause}", tuple(params))
            total = cursor.fetchone()[0]

            query = f"""
                SELECT * FROM second_brain_notes
                {where_clause}
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
            """
            cursor.execute(query, tuple(params + [limit, offset]))
            items = [self._row_to_note_dict(row) for row in cursor.fetchall()]

            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "items": items,
            }

    def update_note(
        self,
        note_id: int,
        category: Optional[str] = None,
        content: Optional[str] = None,
        status: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> bool:
        """Met à jour partiellement une note."""
        fields = []
        params: List[Any] = []

        if category is not None:
            fields.append("category = ?")
            params.append(category)
        if content is not None:
            fields.append("content = ?")
            params.append(content)
        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if tags is not None:
            fields.append("tags = ?")
            params.append(json.dumps(tags, ensure_ascii=False))

        if not fields:
            return False

        fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(note_id)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE second_brain_notes SET {', '.join(fields)} WHERE id = ?",
                tuple(params),
            )
            return cursor.rowcount > 0

    def delete_note(self, note_id: int) -> bool:
        """Supprime définitivement une note."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM second_brain_notes WHERE id = ?", (note_id,))
            return cursor.rowcount > 0

    def get_notes_stats(self) -> Dict[str, int]:
        """Retourne le comptage des notes actives par catégorie."""
        categories = ["dev_idea", "bug_report", "thought", "preference", "task"]
        stats = {c: 0 for c in categories}
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT category, COUNT(*) as cnt
                FROM second_brain_notes
                WHERE status = 'active'
                GROUP BY category
                """
            )
            for row in cursor.fetchall():
                cat = row["category"]
                stats[cat] = row["cnt"]
        return stats

    @staticmethod
    def _row_to_note_dict(row: sqlite3.Row) -> Dict[str, Any]:
        """Convertit un row SQLite en dictionnaire avec parsing des tags."""
        data = dict(row)
        tags_raw = data.get("tags")
        if isinstance(tags_raw, str):
            try:
                data["tags"] = json.loads(tags_raw)
            except Exception:
                data["tags"] = [t.strip() for t in tags_raw.split(",") if t.strip()]
        return data
