"""Socle de base de données unifiée SQLite pour Personal Assistant Hub.

Gère la persistance locale haute performance (< 1ms, mode WAL) :
- Journalisation conversationnelle et audit (conversation_logs)
- Feedbacks et corrections (conversation_feedbacks)
- Règles apprises à la voix (user_learnings)
- Second cerveau compartimenté (second_brain_notes)
"""
from contextlib import contextmanager
from datetime import date, datetime
import json
import logging
import os
import sqlite3
from typing import Any, Dict, Generator, List, Optional, Union

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

            # 5. Séances de sport (sport_sessions)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sport_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    semaine INTEGER NOT NULL,
                    statut TEXT NOT NULL DEFAULT 'Prévu',
                    type_seance TEXT NOT NULL DEFAULT 'EF',
                    distance_km REAL,
                    denivele_d_plus INTEGER DEFAULT 0,
                    duree_secondes INTEGER,
                    ressenti_rpe INTEGER,
                    fc_moyenne INTEGER,
                    fc_max INTEGER,
                    meteo_note INTEGER,
                    programme TEXT DEFAULT '',
                    remarques TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    allure_cible TEXT,
                    vitesse_cible TEXT,
                    strava_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_sport_sessions_date ON sport_sessions(date DESC);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_sport_sessions_semaine ON sport_sessions(semaine);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_sport_sessions_type ON sport_sessions(type_seance);"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_sport_sessions_statut ON sport_sessions(statut);"
            )

            # 6. Synthèses hebdomadaires sport (sport_weekly_summaries)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sport_weekly_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    semaine INTEGER NOT NULL,
                    annee INTEGER NOT NULL,
                    nb_seances INTEGER NOT NULL DEFAULT 0,
                    km_total REAL NOT NULL DEFAULT 0.0,
                    d_plus_total INTEGER NOT NULL DEFAULT 0,
                    km_effort_total REAL NOT NULL DEFAULT 0.0,
                    duree_secondes INTEGER NOT NULL DEFAULT 0,
                    charge_rpe_totale INTEGER NOT NULL DEFAULT 0,
                    nb_renfo INTEGER NOT NULL DEFAULT 0,
                    previous_week_km_effort REAL,
                    vitesse_moyenne_kmh REAL,
                    previous_week_vitesse_kmh REAL,
                    previous_week_charge_rpe INTEGER,
                    duree_course_secondes INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(semaine, annee)
                );
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_sport_summaries_semaine_annee ON sport_weekly_summaries(annee DESC, semaine DESC);"
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

    # ========================================================================
    # Second Cerveau Compartimenté (second_brain_notes)
    # ========================================================================

    def add_note(
        self,
        category: str,
        content: str,
        tags: Optional[List[str]] = None,
        status: str = "active",
    ) -> int:
        """Ajoute une note dans le second cerveau."""
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO second_brain_notes (category, content, tags, status)
                VALUES (?, ?, ?, ?)
                """,
                (category, content, tags_json, status),
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
                ORDER BY id DESC
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

    # ========================================================================
    # Auto-Apprentissage Vocal (user_learnings)
    # ========================================================================

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

    # =========================================================================
    # Module Sport (sport_sessions & sport_weekly_summaries)
    # =========================================================================

    def add_sport_session(self, session_data: Dict[str, Any]) -> int:
        """Insère une nouvelle séance sportive dans sport_sessions."""
        data = dict(session_data)
        date_val = str(data.get("date", "")).strip()
        if not date_val:
            raise ValueError("Le champ 'date' est obligatoire pour enregistrer une séance de sport.")

        # Calcul automatique du numéro de semaine si absent
        semaine = data.get("semaine")
        if semaine is None:
            try:
                d_obj = datetime.strptime(date_val, "%Y-%m-%d").date()
                semaine = d_obj.isocalendar()[1]
            except Exception:
                semaine = 1

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO sport_sessions (
                    date, semaine, statut, type_seance, distance_km,
                    denivele_d_plus, duree_secondes, ressenti_rpe,
                    fc_moyenne, fc_max, meteo_note, programme,
                    remarques, notes, allure_cible, vitesse_cible, strava_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    date_val,
                    int(semaine),
                    str(data.get("statut", "Prévu")),
                    str(data.get("type_seance", "EF")),
                    float(data["distance_km"]) if data.get("distance_km") is not None else None,
                    int(data.get("denivele_d_plus", 0) or 0),
                    int(data["duree_secondes"]) if data.get("duree_secondes") is not None else None,
                    int(data["ressenti_rpe"]) if data.get("ressenti_rpe") is not None else None,
                    int(data["fc_moyenne"]) if data.get("fc_moyenne") is not None else None,
                    int(data["fc_max"]) if data.get("fc_max") is not None else None,
                    int(data["meteo_note"]) if data.get("meteo_note") is not None else None,
                    str(data.get("programme") or ""),
                    str(data.get("remarques") or ""),
                    str(data.get("notes") or ""),
                    data.get("allure_cible"),
                    data.get("vitesse_cible"),
                    data.get("strava_id"),
                ),
            )
            return cursor.lastrowid

    def get_sport_session_by_id(self, session_id: int) -> Optional[Dict[str, Any]]:
        """Récupère une séance sportive par son identifiant unique."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sport_sessions WHERE id = ?", (session_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_sport_session_by_date(self, target_date: Union[str, date]) -> Optional[Dict[str, Any]]:
        """Récupère la séance la plus récente enregistrée à une date donnée."""
        date_str = target_date.isoformat() if isinstance(target_date, (date, datetime)) else str(target_date).strip()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM sport_sessions WHERE date = ? ORDER BY id DESC LIMIT 1",
                (date_str,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_sport_sessions(
        self,
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        week: Optional[int] = None,
        year: Optional[int] = None,
        session_type: Optional[str] = None,
        status: Optional[str] = None,
        order_desc: bool = False,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Récupère une liste filtrée de séances sportives."""
        conditions = []
        params: List[Any] = []

        if start_date is not None:
            s_str = start_date.isoformat() if isinstance(start_date, (date, datetime)) else str(start_date).strip()
            conditions.append("date >= ?")
            params.append(s_str)

        if end_date is not None:
            e_str = end_date.isoformat() if isinstance(end_date, (date, datetime)) else str(end_date).strip()
            conditions.append("date <= ?")
            params.append(e_str)

        if week is not None:
            conditions.append("semaine = ?")
            params.append(week)

        if year is not None:
            conditions.append("substr(date, 1, 4) = ?")
            params.append(str(year))

        if session_type is not None:
            conditions.append("type_seance = ?")
            params.append(session_type)

        if status is not None:
            conditions.append("statut = ?")
            params.append(status)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        order_dir = "DESC" if order_desc else "ASC"
        query = f"SELECT * FROM sport_sessions {where_clause} ORDER BY date {order_dir}, id {order_dir}"

        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            return [dict(row) for row in cursor.fetchall()]

    def get_last_sport_session(
        self,
        session_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Résout la dernière séance enregistrée (triée par date antichronologique puis id)."""
        conditions = []
        params: List[Any] = []

        if session_type:
            conditions.append("type_seance = ?")
            params.append(session_type)
        if status:
            conditions.append("statut = ?")
            params.append(status)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM sport_sessions {where_clause} ORDER BY date DESC, id DESC LIMIT 1"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_sport_session(self, session_id: int, updates: Dict[str, Any]) -> bool:
        """Met à jour une séance sportive existante."""
        allowed_fields = {
            "date", "semaine", "statut", "type_seance", "distance_km",
            "denivele_d_plus", "duree_secondes", "ressenti_rpe",
            "fc_moyenne", "fc_max", "meteo_note", "programme",
            "remarques", "notes", "allure_cible", "vitesse_cible", "strava_id",
        }
        fields = []
        params: List[Any] = []

        for key, val in updates.items():
            if key in allowed_fields:
                fields.append(f"{key} = ?")
                params.append(val)

        if not fields:
            return False

        fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(session_id)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE sport_sessions SET {', '.join(fields)} WHERE id = ?",
                tuple(params),
            )
            return cursor.rowcount > 0

    def delete_sport_session(self, session_id: int) -> bool:
        """Supprime une séance sportive."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sport_sessions WHERE id = ?", (session_id,))
            return cursor.rowcount > 0

    def upsert_sport_weekly_summary(self, summary_data: Dict[str, Any]) -> int:
        """Insère ou met à jour la synthèse hebdomadaire d'une semaine/année."""
        data = dict(summary_data)
        semaine = int(data["semaine"])
        annee = int(data["annee"])

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO sport_weekly_summaries (
                    semaine, annee, nb_seances, km_total, d_plus_total,
                    km_effort_total, duree_secondes, charge_rpe_totale,
                    nb_renfo, previous_week_km_effort, vitesse_moyenne_kmh,
                    previous_week_vitesse_kmh, previous_week_charge_rpe,
                    duree_course_secondes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(semaine, annee) DO UPDATE SET
                    nb_seances = excluded.nb_seances,
                    km_total = excluded.km_total,
                    d_plus_total = excluded.d_plus_total,
                    km_effort_total = excluded.km_effort_total,
                    duree_secondes = excluded.duree_secondes,
                    charge_rpe_totale = excluded.charge_rpe_totale,
                    nb_renfo = excluded.nb_renfo,
                    previous_week_km_effort = excluded.previous_week_km_effort,
                    vitesse_moyenne_kmh = excluded.vitesse_moyenne_kmh,
                    previous_week_vitesse_kmh = excluded.previous_week_vitesse_kmh,
                    previous_week_charge_rpe = excluded.previous_week_charge_rpe,
                    duree_course_secondes = excluded.duree_course_secondes,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    semaine,
                    annee,
                    int(data.get("nb_seances", 0)),
                    float(data.get("km_total", 0.0)),
                    int(data.get("d_plus_total", 0)),
                    float(data.get("km_effort_total", 0.0)),
                    int(data.get("duree_secondes", 0)),
                    int(data.get("charge_rpe_totale", 0)),
                    int(data.get("nb_renfo", 0)),
                    float(data["previous_week_km_effort"]) if data.get("previous_week_km_effort") is not None else None,
                    float(data["vitesse_moyenne_kmh"]) if data.get("vitesse_moyenne_kmh") is not None else None,
                    float(data["previous_week_vitesse_kmh"]) if data.get("previous_week_vitesse_kmh") is not None else None,
                    int(data["previous_week_charge_rpe"]) if data.get("previous_week_charge_rpe") is not None else None,
                    int(data["duree_course_secondes"]) if data.get("duree_course_secondes") is not None else None,
                ),
            )
            # Récupération de l'id
            cursor.execute(
                "SELECT id FROM sport_weekly_summaries WHERE semaine = ? AND annee = ?",
                (semaine, annee),
            )
            row = cursor.fetchone()
            return row["id"] if row else cursor.lastrowid

    def get_sport_weekly_summary(self, semaine: int, annee: int) -> Optional[Dict[str, Any]]:
        """Récupère la synthèse d'une semaine et année précises."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM sport_weekly_summaries WHERE semaine = ? AND annee = ?",
                (semaine, annee),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_sport_weekly_summaries(self, annee: Optional[int] = None) -> List[Dict[str, Any]]:
        """Récupère l'ensemble des synthèses hebdomadaires ordonnées chronologiquement."""
        query = "SELECT * FROM sport_weekly_summaries"
        params: List[Any] = []
        if annee is not None:
            query += " WHERE annee = ?"
            params.append(annee)
        query += " ORDER BY annee ASC, semaine ASC"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            return [dict(row) for row in cursor.fetchall()]

    def delete_sport_weekly_summary(self, semaine: int, annee: int) -> bool:
        """Supprime une synthèse hebdomadaire."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM sport_weekly_summaries WHERE semaine = ? AND annee = ?",
                (semaine, annee),
            )
            return cursor.rowcount > 0




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
