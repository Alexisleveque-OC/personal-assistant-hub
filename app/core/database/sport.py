"""Séances de sport et synthèses hebdomadaires (sport_sessions, sport_weekly_summaries)."""
from datetime import date, datetime, timedelta
import sqlite3
from typing import Any, Dict, List, Optional, Union

from app.core.database.base import SQLiteBase


class SportStore(SQLiteBase):
    """Tables sport_sessions et sport_weekly_summaries."""

    @staticmethod
    def _create_sport_schema(cursor: sqlite3.Cursor) -> None:
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
        # Refonte UX (10/11) : douleur de la séance (0-10, vide = jamais renseignée) et zone ; ajout idempotent
        # sur les bases existantes, sans reprise de l'historique.
        existing_columns = {row[1] for row in cursor.execute("PRAGMA table_info(sport_sessions)")}
        for column, ddl in (("douleur_intensite", "INTEGER"), ("douleur_zone", "TEXT")):
            if column not in existing_columns:
                cursor.execute(f"ALTER TABLE sport_sessions ADD COLUMN {column} {ddl}")

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
                    remarques, notes, allure_cible, vitesse_cible, strava_id,
                    douleur_intensite, douleur_zone
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    int(data["douleur_intensite"]) if data.get("douleur_intensite") is not None else None,
                    data.get("douleur_zone"),
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

        if week is not None and year is not None:
            # Semaine ISO d'une année ISO : du lundi au dimanche, même à cheval sur deux années civiles.
            monday = date.fromisocalendar(year, week, 1)
            conditions.append("date BETWEEN ? AND ?")
            params.extend([monday.isoformat(), (monday + timedelta(days=6)).isoformat()])
        elif week is not None:
            conditions.append("semaine = ?")
            params.append(week)
        elif year is not None:
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
        max_date: Optional[str] = None,
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
        if max_date:
            conditions.append("date <= ?")
            params.append(max_date)

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
            "douleur_intensite", "douleur_zone",
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
