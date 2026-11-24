"""Noms de catégorie budget appris à la voix (budget_category_aliases) : « loisir alexis » → Loisir Alex.

Gardés dans la base de l'app et non dans l'onglet `Tri auto` du classeur, que l'import bancaire utilise pour classer
les libellés de banque (décision utilisateur du 24/11/2026).
"""
import sqlite3
from typing import Dict, Optional

from app.core.database.base import SQLiteBase


class BudgetAliasStore(SQLiteBase):
    """Table budget_category_aliases : nom dit (normalisé, sans accents ni casse) → catégorie exacte du classeur."""

    @staticmethod
    def _create_budget_aliases_schema(cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS budget_category_aliases (
                alias TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

    def learn_budget_alias(self, alias: str, category: str) -> None:
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO budget_category_aliases (alias, category) VALUES (?, ?) "
                "ON CONFLICT(alias) DO UPDATE SET category = excluded.category, created_at = CURRENT_TIMESTAMP",
                (alias, category),
            )

    def get_budget_alias(self, alias: str) -> Optional[str]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT category FROM budget_category_aliases WHERE alias = ?", (alias,)).fetchone()
        return None if row is None else row[0]

    def forget_budget_alias(self, alias: str) -> bool:
        with self.get_connection() as conn:
            return conn.execute("DELETE FROM budget_category_aliases WHERE alias = ?", (alias,)).rowcount > 0

    def list_budget_aliases(self) -> Dict[str, str]:
        with self.get_connection() as conn:
            rows = conn.execute("SELECT alias, category FROM budget_category_aliases ORDER BY alias").fetchall()
        return {alias: category for alias, category in rows}
