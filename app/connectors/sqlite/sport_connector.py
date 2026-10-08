"""Connecteur de persistance SQLite pour le suivi de course à pied et Mini-Coach Otis.

Fournit une latence < 1 ms en mode WAL, l'indépendance totale de l'API Google Sheets
et une parité fonctionnelle stricte avec SportConnector.
"""
from datetime import date, datetime, timedelta
import logging
from typing import Any, Dict, List, Optional, Union

from app.connectors.base import BaseConnector
from app.connectors.sheets.sport_models import (
    SportSession,
    SportSessionCreate,
    SportSessionPlan,
    SportSessionStatus,
    SportSessionType,
    SportSessionUpdate,
    SportWeeklySummary,
    calculate_km_effort,
    calculate_speed_kmh,
    calculate_pace_min_km,
    format_pace,
)
from app.core.database import DatabaseManager, get_database_manager

logger = logging.getLogger(__name__)


def _parse_date(val: Any) -> Optional[date]:
    """Parse une date de manière robuste."""
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if not val or not str(val).strip():
        return None
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


class SqlSportConnector(BaseConnector):
    """Connecteur SQLite haute performance (< 1ms) pour le sport et le coaching Otis."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db = db_manager or get_database_manager()

    @property
    def name(self) -> str:
        return "sqlite_sport"

    async def is_healthy(self) -> bool:
        """Vérifie si la base SQLite est accessible et initialisée."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM sport_sessions LIMIT 1;")
                return True
        except Exception as exc:
            logger.warning(f"Erreur health check SqlSportConnector : {exc}")
            return False

    def invalidate_cache(self) -> None:
        """Compatibilité d'interface (invalidation sans coût en SQLite WAL)."""
        pass

    def _row_to_sport_session(self, row: Dict[str, Any]) -> SportSession:
        """Convertit un dictionnaire / row SQLite en modèle Pydantic SportSession."""
        d_val = _parse_date(row["date"]) or date.today()
        statut_raw = row.get("statut") or "Prévu"
        type_raw = row.get("type_seance") or "EF"

        # Normalisation du statut
        try:
            statut = SportSessionStatus(statut_raw)
        except ValueError:
            statut = SportSessionStatus.PLANIFIE

        # Normalisation du type de séance
        clean_type = str(type_raw).strip()
        if clean_type.lower() in ("renfo", "renforcement", "ppg", "musculation"):
            type_seance = SportSessionType.RENFORCEMENT
        else:
            try:
                type_seance = SportSessionType(clean_type)
            except ValueError:
                type_seance = SportSessionType.EF

        return SportSession(
            date=d_val,
            semaine=int(row.get("semaine") or d_val.isocalendar()[1]),
            statut=statut,
            type_seance=type_seance,
            distance_km=float(row["distance_km"]) if row.get("distance_km") is not None else None,
            denivele_d_plus=int(row.get("denivele_d_plus", 0) or 0),
            duree_secondes=int(row["duree_secondes"]) if row.get("duree_secondes") is not None else None,
            ressenti_rpe=int(row["ressenti_rpe"]) if row.get("ressenti_rpe") is not None else None,
            fc_moyenne=int(row["fc_moyenne"]) if row.get("fc_moyenne") is not None else None,
            fc_max=int(row["fc_max"]) if row.get("fc_max") is not None else None,
            meteo_note=int(row["meteo_note"]) if row.get("meteo_note") is not None else None,
            programme=row.get("programme") or "",
            remarques=row.get("remarques") or "",
            notes=row.get("notes") or "",
            allure_cible=row.get("allure_cible"),
            vitesse_cible=row.get("vitesse_cible"),
            strava_id=row.get("strava_id"),
        )

    def get_all_sessions(self) -> List[SportSession]:
        """Récupère l'ensemble des séances enregistrées dans SQLite ordonnées chronologiquement."""
        rows = self.db.get_sport_sessions()
        return [self._row_to_sport_session(r) for r in rows]

    def get_session(self, target_date: Optional[Union[date, str]] = None) -> Optional[SportSession]:
        """Récupère la séance du jour ou d'une date cible."""
        t_date = _parse_date(target_date) if target_date else date.today()
        if not t_date:
            return None
        row = self.db.get_sport_session_by_date(t_date.isoformat())
        return self._row_to_sport_session(row) if row else None

    def get_week_sessions(self, week_num: int, year: Optional[int] = None) -> List[SportSession]:
        """Récupère les séances d'une semaine ISO donnée."""
        rows = self.db.get_sport_sessions(week=week_num, year=year)
        return [self._row_to_sport_session(r) for r in rows]

    def get_last_session(
        self,
        session_type: Optional[Union[SportSessionType, str]] = None,
        status: Optional[Union[SportSessionStatus, str]] = SportSessionStatus.REALISE,
    ) -> Optional[SportSession]:
        """Récupère la dernière séance enregistrée en base (filtrée par statut et type optionnel)."""
        type_str = None
        if session_type:
            if isinstance(session_type, SportSessionType):
                type_str = session_type.value
            else:
                clean = str(session_type).strip().lower()
                if clean in ("renfo", "renforcement", "ppg", "musculation"):
                    type_str = SportSessionType.RENFORCEMENT.value
                elif clean in ("footing", "ef", "course"):
                    type_str = SportSessionType.EF.value
                elif clean in ("fractionné", "fractionne"):
                    type_str = SportSessionType.FRACTIONNE.value
                elif clean in ("sortie longue", "longue"):
                    type_str = SportSessionType.SORTIE_LONGUE.value
                else:
                    try:
                        type_str = SportSessionType(str(session_type)).value
                    except ValueError:
                        type_str = str(session_type)

        statut_str = None
        if status:
            statut_str = status.value if hasattr(status, "value") else str(status)

        row = self.db.get_last_sport_session(session_type=type_str, status=statut_str)
        return self._row_to_sport_session(row) if row else None

    def log_session(self, session_data: SportSessionCreate) -> SportSession:
        """Enregistre ou met à jour une séance terminée dans SQLite et met à jour la synthèse."""
        target_date = session_data.date or date.today()
        date_iso = target_date.isoformat()
        semaine = target_date.isocalendar()[1]

        # Vérifier si une séance existe déjà pour cette date
        existing = self.db.get_sport_session_by_date(date_iso)

        final_type = session_data.type_seance
        final_prog = session_data.programme or ""
        final_rem = session_data.remarques or session_data.notes or ""

        if existing:
            # Préserver le type ou programme prévu si log rapide par défaut
            ex_type = existing.get("type_seance")
            if session_data.type_seance == SportSessionType.EF and ex_type and ex_type != "EF":
                try:
                    final_type = SportSessionType(ex_type)
                except ValueError:
                    pass
            if not final_prog:
                final_prog = existing.get("programme") or ""
            if not final_rem:
                final_rem = existing.get("remarques") or existing.get("notes") or ""

            updates = {
                "statut": SportSessionStatus.REALISE.value,
                "type_seance": final_type.value,
                "distance_km": session_data.distance_km,
                "denivele_d_plus": session_data.denivele_d_plus or 0,
                "duree_secondes": session_data.duree_secondes,
                "ressenti_rpe": session_data.ressenti_rpe,
                "fc_moyenne": session_data.fc_moyenne,
                "fc_max": session_data.fc_max,
                "meteo_note": session_data.meteo_note,
                "programme": final_prog,
                "remarques": final_rem,
                "notes": final_rem,
                "strava_id": session_data.strava_id or existing.get("strava_id"),
            }
            self.db.update_sport_session(existing["id"], updates)
        else:
            insert_data = {
                "date": date_iso,
                "semaine": semaine,
                "statut": SportSessionStatus.REALISE.value,
                "type_seance": final_type.value,
                "distance_km": session_data.distance_km,
                "denivele_d_plus": session_data.denivele_d_plus or 0,
                "duree_secondes": session_data.duree_secondes,
                "ressenti_rpe": session_data.ressenti_rpe,
                "fc_moyenne": session_data.fc_moyenne,
                "fc_max": session_data.fc_max,
                "meteo_note": session_data.meteo_note,
                "programme": final_prog,
                "remarques": final_rem,
                "notes": final_rem,
                "allure_cible": None,
                "vitesse_cible": None,
                "strava_id": session_data.strava_id,
            }
            self.db.add_sport_session(insert_data)

        # Mettre à jour la synthèse hebdomadaire correspondante
        self.get_weekly_summary(week_num=semaine, year=target_date.year)

        saved = self.get_session(target_date)
        if not saved:
            raise RuntimeError(f"Échec de récupération de la séance enregistrée pour {date_iso}")
        return saved

    def plan_session(
        self,
        plan_data: Optional[SportSessionPlan] = None,
        session_date: Optional[Union[date, str]] = None,
        type_seance: Optional[Union[SportSessionType, str]] = None,
        distance_km: Optional[float] = None,
        notes: Optional[str] = None,
        programme: Optional[str] = None,
        remarques: Optional[str] = None,
        allure_cible: Optional[str] = None,
        vitesse_cible: Optional[str] = None,
    ) -> SportSession:
        """Planifie ou met à jour une séance future dans SQLite."""
        if plan_data is None:
            t_date = _parse_date(session_date) or (date.today() + timedelta(days=1))
            t_enum = SportSessionType.EF
            if isinstance(type_seance, SportSessionType):
                t_enum = type_seance
            elif isinstance(type_seance, str):
                try:
                    t_enum = SportSessionType(type_seance)
                except ValueError:
                    t_enum = SportSessionType.EF

            plan = SportSessionPlan(
                date=t_date,
                type_seance=t_enum,
                distance_km_cible=distance_km,
                programme=programme or notes or "",
                remarques=remarques or "",
                notes=notes or programme or "",
                allure_cible=allure_cible,
                vitesse_cible=vitesse_cible,
            )
        else:
            plan = plan_data

        target_date = plan.date
        date_iso = target_date.isoformat()
        semaine = target_date.isocalendar()[1]

        existing = self.db.get_sport_session_by_date(date_iso)
        if existing:
            updates = {
                "statut": SportSessionStatus.PLANIFIE.value,
                "type_seance": plan.type_seance.value,
                "programme": plan.programme or existing.get("programme") or "",
                "remarques": plan.remarques or existing.get("remarques") or "",
                "notes": plan.notes or existing.get("notes") or "",
                "allure_cible": plan.allure_cible,
                "vitesse_cible": plan.vitesse_cible,
            }
            if plan.distance_km_cible is not None:
                updates["distance_km"] = plan.distance_km_cible
            if plan.duree_cible_secondes is not None:
                updates["duree_secondes"] = plan.duree_cible_secondes
            self.db.update_sport_session(existing["id"], updates)
        else:
            insert_data = {
                "date": date_iso,
                "semaine": semaine,
                "statut": SportSessionStatus.PLANIFIE.value,
                "type_seance": plan.type_seance.value,
                "distance_km": plan.distance_km_cible,
                "denivele_d_plus": 0,
                "duree_secondes": plan.duree_cible_secondes,
                "programme": plan.programme or "",
                "remarques": plan.remarques or "",
                "notes": plan.notes or "",
                "allure_cible": plan.allure_cible,
                "vitesse_cible": plan.vitesse_cible,
            }
            self.db.add_sport_session(insert_data)

        saved = self.get_session(target_date)
        if not saved:
            raise RuntimeError(f"Échec de récupération de la séance planifiée pour {date_iso}")
        return saved

    def plan_weekly_sessions(self, plans: List[SportSessionPlan]) -> List[SportSession]:
        """Planifie un ensemble de séances pour une semaine."""
        results: List[SportSession] = []
        for p in plans:
            results.append(self.plan_session(p))
        return results

    def update_session(
        self,
        target_date: Union[date, str],
        updates: Union[SportSessionUpdate, Dict[str, Any]],
        target_type: Optional[SportSessionType] = None,
    ) -> SportSession:
        """Met à jour les attributs d'une séance existante."""
        t_date = _parse_date(target_date)
        if not t_date:
            raise ValueError(f"Date invalide : {target_date}")
        date_iso = t_date.isoformat()

        # Chercher la séance avec éventuellement le type cible
        existing = None
        if target_type:
            sessions = self.db.get_sport_sessions(start_date=date_iso, end_date=date_iso, session_type=target_type.value)
            if sessions:
                existing = sessions[0]
        if not existing:
            existing = self.db.get_sport_session_by_date(date_iso)

        if not existing:
            # Création automatique minimale si la séance n'existe pas encore
            session_id = self.db.add_sport_session({
                "date": date_iso,
                "semaine": t_date.isocalendar()[1],
                "statut": "Prévu",
                "type_seance": target_type.value if target_type else "EF",
            })
            existing = self.db.get_sport_session_by_id(session_id)

        update_dict: Dict[str, Any] = (
            updates.model_dump(exclude_unset=True) if isinstance(updates, SportSessionUpdate) else dict(updates)
        )

        # Gestion de append_remarques / append_notes
        if update_dict.get("append_remarques") or update_dict.get("append_notes"):
            new_rem = update_dict.get("remarques") or update_dict.get("notes") or ""
            old_rem = existing.get("remarques") or existing.get("notes") or ""
            if old_rem.strip() and new_rem.strip():
                comb = f"{old_rem.strip()} | {new_rem.strip()}"
                update_dict["remarques"] = comb
                update_dict["notes"] = comb

        # Transition automatique vers Réalisé si métriques réelles enregistrées sur une séance prévue
        if "statut" not in update_dict and existing.get("statut") == SportSessionStatus.PLANIFIE.value:
            if any(k in update_dict for k in ("distance_km", "duree_secondes", "ressenti_rpe")):
                update_dict["statut"] = SportSessionStatus.REALISE.value

        # Normalisation des Enums
        if "statut" in update_dict:
            s_val = update_dict["statut"]
            update_dict["statut"] = s_val.value if hasattr(s_val, "value") else str(s_val)
        if "type_seance" in update_dict:
            t_val = update_dict["type_seance"]
            update_dict["type_seance"] = t_val.value if hasattr(t_val, "value") else str(t_val)

        self.db.update_sport_session(existing["id"], update_dict)

        # Mettre à jour la synthèse
        self.get_weekly_summary(week_num=t_date.isocalendar()[1], year=t_date.year)

        saved = self.get_session(t_date)
        if not saved:
            raise RuntimeError(f"Échec de récupération de la séance après modification ({date_iso})")
        return saved

    def get_weekly_summary(
        self,
        week_num: Optional[int] = None,
        year: Optional[int] = None,
        semaine: Optional[int] = None,
        annee: Optional[int] = None,
    ) -> SportWeeklySummary:
        """Calcule la synthèse hebdomadaire multicritère et persiste les métriques dans SQLite."""
        target_week = week_num or semaine or datetime.now().isocalendar()[1]
        target_year = year or annee or datetime.now().year

        # Récupération des séances réelles de la semaine
        all_week_sessions = self.get_week_sessions(target_week, target_year)
        realised_sessions = [s for s in all_week_sessions if s.statut == SportSessionStatus.REALISE]

        nb_seances = len(realised_sessions)
        km_total = sum(s.distance_km or 0.0 for s in realised_sessions)
        d_plus_total = sum(s.denivele_d_plus or 0 for s in realised_sessions)
        km_effort_total = sum(s.km_effort or 0.0 for s in realised_sessions)
        duree_secondes = sum(s.duree_secondes or 0 for s in realised_sessions)
        charge_rpe_totale = sum(s.charge_rpe or 0 for s in realised_sessions)
        nb_renfo = sum(1 for s in realised_sessions if s.type_seance == SportSessionType.RENFORCEMENT)

        running_sessions = [
            s for s in realised_sessions
            if s.type_seance != SportSessionType.RENFORCEMENT and (s.distance_km or 0) > 0
        ]
        duree_course_sec = sum(s.duree_secondes or 0 for s in running_sessions)
        cur_vitesse = (
            calculate_speed_kmh(km_total, duree_course_sec)
            if duree_course_sec > 0
            else calculate_speed_kmh(km_total, duree_secondes)
        )

        # Récupération de la semaine précédente (S-1)
        prev_iso = (date.fromisocalendar(target_year, target_week, 1) - timedelta(days=7)).isocalendar()
        prev_week, prev_year = prev_iso[1], prev_iso[0]

        prev_summary = self.db.get_sport_weekly_summary(prev_week, prev_year)
        if prev_summary:
            prev_km_effort = prev_summary.get("km_effort_total")
            prev_vitesse = prev_summary.get("vitesse_moyenne_kmh")
            prev_charge_rpe = prev_summary.get("charge_rpe_totale")
        else:
            prev_sessions = [s for s in self.get_week_sessions(prev_week, prev_year) if s.statut == SportSessionStatus.REALISE]
            if prev_sessions:
                prev_km_effort = sum(s.km_effort or 0.0 for s in prev_sessions)
                prev_charge_rpe = sum(s.charge_rpe or 0 for s in prev_sessions)
                prev_running = [s for s in prev_sessions if s.type_seance != SportSessionType.RENFORCEMENT and (s.distance_km or 0) > 0]
                p_km = sum(s.distance_km or 0.0 for s in prev_running)
                p_dur = sum(s.duree_secondes or 0 for s in prev_running)
                prev_vitesse = calculate_speed_kmh(p_km, p_dur) if (p_km > 0 and p_dur > 0) else None
            else:
                prev_km_effort = None
                prev_vitesse = None
                prev_charge_rpe = None

        # Persistance dans SQLite
        summary_payload = {
            "semaine": target_week,
            "annee": target_year,
            "nb_seances": nb_seances,
            "km_total": round(km_total, 2),
            "d_plus_total": d_plus_total,
            "km_effort_total": round(km_effort_total, 2),
            "duree_secondes": duree_secondes,
            "charge_rpe_totale": charge_rpe_totale,
            "nb_renfo": nb_renfo,
            "previous_week_km_effort": prev_km_effort,
            "vitesse_moyenne_kmh": cur_vitesse,
            "previous_week_vitesse_kmh": prev_vitesse,
            "previous_week_charge_rpe": prev_charge_rpe,
            "duree_course_secondes": duree_course_sec,
        }
        self.db.upsert_sport_weekly_summary(summary_payload)

        return SportWeeklySummary(
            semaine=target_week,
            annee=target_year,
            nb_seances=nb_seances,
            km_total=round(km_total, 2),
            d_plus_total=d_plus_total,
            km_effort_total=round(km_effort_total, 2),
            duree_secondes=duree_secondes,
            duree_course_secondes=duree_course_sec,
            vitesse_moyenne_kmh=cur_vitesse,
            charge_rpe_totale=charge_rpe_totale,
            nb_renfo=nb_renfo,
            previous_week_km_effort=prev_km_effort,
            previous_week_vitesse_kmh=prev_vitesse,
            previous_week_charge_rpe=prev_charge_rpe,
        )

    def get_all_summaries(self, year: Optional[int] = None) -> List[SportWeeklySummary]:
        """Retourne la liste de toutes les synthèses hebdomadaires ordonnées de façon décroissante."""
        rows = self.db.get_all_sport_weekly_summaries(annee=year)
        # Si la table est vide mais qu'il y a des séances, on auto-calcule les semaines distinctes
        if not rows:
            sessions = self.db.get_sport_sessions(year=year)
            distinct_weeks = sorted({(s["semaine"], int(s["date"][:4])) for s in sessions})
            for w, y in distinct_weeks:
                self.get_weekly_summary(week_num=w, year=y)
            rows = self.db.get_all_sport_weekly_summaries(annee=year)

        results: List[SportWeeklySummary] = []
        for r in rows:
            results.append(
                SportWeeklySummary(
                    semaine=r["semaine"],
                    annee=r["annee"],
                    nb_seances=r["nb_seances"],
                    km_total=r["km_total"],
                    d_plus_total=r["d_plus_total"],
                    km_effort_total=r["km_effort_total"],
                    duree_secondes=r["duree_secondes"],
                    duree_course_secondes=r.get("duree_course_secondes"),
                    vitesse_moyenne_kmh=r.get("vitesse_moyenne_kmh"),
                    charge_rpe_totale=r["charge_rpe_totale"],
                    nb_renfo=r["nb_renfo"],
                    previous_week_km_effort=r.get("previous_week_km_effort"),
                    previous_week_vitesse_kmh=r.get("previous_week_vitesse_kmh"),
                    previous_week_charge_rpe=r.get("previous_week_charge_rpe"),
                )
            )
        results.sort(key=lambda s: (s.annee, s.semaine), reverse=True)
        return results

    async def execute_action(self, action_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Exécute une action standardisée sur le connecteur sport."""
        if action_name == "get_session":
            s = self.get_session(parameters.get("target_date"))
            return s.model_dump() if s else {}
        elif action_name == "log_session":
            req = SportSessionCreate(**parameters)
            saved = self.log_session(req)
            return saved.model_dump()
        elif action_name == "plan_session":
            plan = SportSessionPlan(**parameters)
            saved = self.plan_session(plan)
            return saved.model_dump()
        elif action_name == "get_weekly_summary":
            summary = self.get_weekly_summary(
                week_num=parameters.get("week_num") or parameters.get("semaine"),
                year=parameters.get("year") or parameters.get("annee"),
            )
            return summary.model_dump()
        else:
            raise NotImplementedError(f"Action '{action_name}' non supportée par SqlSportConnector.")
