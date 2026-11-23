"""Consommation de l'API payante Claude (llm_usage) : une ligne par appel de l'expert, base du garde-fou mensuel."""
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.database.base import SQLiteBase


class LlmUsageStore(SQLiteBase):
    """Table llm_usage."""

    @staticmethod
    def _create_llm_usage_schema(cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                cache_read_tokens INTEGER NOT NULL,
                cache_creation_tokens INTEGER NOT NULL,
                cost_usd REAL NOT NULL,
                session_id TEXT
            );
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_created_at ON llm_usage(created_at);")

    def add_llm_usage(
        self, model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int, cache_creation_tokens: int,
        cost_usd: float, session_id: Optional[str], created_at: Optional[str] = None,
    ) -> int:
        """`created_at` : horodatage ISO 8601 en UTC (maintenant par défaut)."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO llm_usage (created_at, model, input_tokens, output_tokens, cache_read_tokens,
                                       cache_creation_tokens, cost_usd, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at or datetime.now(timezone.utc).isoformat(), model, input_tokens, output_tokens,
                    cache_read_tokens, cache_creation_tokens, cost_usd, session_id,
                ),
            )
            return int(cursor.lastrowid)

    def get_llm_usage_totals(self, since_iso: str) -> Dict[str, Any]:
        """Coût cumulé et nombre d'appels depuis `since_iso` (inclus), horodatages ISO UTC comparés en texte."""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0), COUNT(*) FROM llm_usage WHERE created_at >= ?", (since_iso,),
            ).fetchone()
        return {"cost_usd": float(row[0]), "calls": int(row[1])}
