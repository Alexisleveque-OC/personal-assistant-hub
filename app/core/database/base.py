"""Connexion SQLite commune aux magasins par domaine (mode WAL, clés étrangères, attente sur verrou)."""
from contextlib import contextmanager
import os
import sqlite3
from typing import Generator, Optional

from app.config import settings


class SQLiteBase:
    """Chemin de la base et connexion : partagés par tous les magasins assemblés dans DatabaseManager."""

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
