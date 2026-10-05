"""Connecteur Google Sheets pour le suivi de course à pied et Mini-Coach (SportConnector)."""
from datetime import date, datetime
import json
import base64
import re
import logging
from typing import Any, Dict, List, Optional, Union

try:
    import gspread
except ImportError:
    gspread = None

from app.config import settings
from app.connectors.base import BaseConnector
from app.connectors.sheets.sport_models import (
    SportSession,
    SportSessionCreate,
    SportSessionPlan,
    SportSessionStatus,
    SportSessionType,
    SportWeeklySummary,
    calculate_km_effort,
    calculate_speed_kmh,
    calculate_pace_min_km,
    format_pace,
)
from app.connectors.sheets.sport_schema import (
    SEANCES_SHEET_ALIASES,
    SYNTHESE_SHEET_ALIASES,
    resolve_worksheet,
)
from app.core.date_resolver import parse_target_date

logger = logging.getLogger(__name__)


def _parse_date_robust(val: Any) -> Optional[date]:
    """Parse une date depuis diverses représentations (date, 'YYYY-MM-DD', 'DD/MM/YYYY', 'DD/MM/YY')."""
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if not val or not str(val).strip():
        return None

    clean_str = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d/%m"):
        try:
            parsed = datetime.strptime(clean_str, fmt)
            if fmt == "%d/%m":
                parsed = parsed.replace(year=datetime.now().year)
            return parsed.date()
        except ValueError:
            continue

    # Dates textuelles françaises (ex: "lun. 28 septembre", "13 septembre 2026")
    months_map = {
        "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
        "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
    }
    match = re.search(r"(\d{1,2})\s+([a-zA-Zéû]+)(?:\s+(\d{4}))?", clean_str.lower())
    if match:
        day = int(match.group(1))
        m_name = match.group(2)
        month = months_map.get(m_name)
        year = int(match.group(3)) if match.group(3) else datetime.now().year
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                pass

    return None


def _parse_duration_seconds(val: Any) -> Optional[int]:
    """Parse une durée vers un nombre de secondes (gère 'hh:mm:ss', 'mm:ss', float fraction de jour)."""
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        # Si c'est un float <= 1.0 (ex: 0.0212), c'est une fraction de jour Google Sheets
        if 0 < val <= 1.0:
            return int(round(val * 86400))
        return int(round(val))

    s = str(val).strip()
    if not s:
        return None

    parts = s.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 1:
            return int(float(parts[0]))
    except ValueError:
        return None
    return None


def _safe_float(val: Any) -> Optional[float]:
    """Nettoie et convertit une valeur en float (gère virgule, 'km', etc.)."""
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).lower().replace("km", "").replace("/km", "").replace(" ", "").replace(",", ".").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _safe_int(val: Any) -> Optional[int]:
    """Nettoie et convertit une valeur en entier."""
    if val is None or val == "":
        return None
    if isinstance(val, int):
        return val
    try:
        return int(round(float(str(val).replace(",", ".").strip())))
    except ValueError:
        return None


class SportConnector(BaseConnector):
    """Connecteur pour le suivi du running, planification et conseils sécurité du Mini-Coach Otis."""

    def __init__(
        self,
        spreadsheet: Optional[Any] = None,
        credentials_path: Optional[str] = None,
    ) -> None:
        if spreadsheet is not None:
            self._spreadsheet = spreadsheet
        else:
            if gspread is None:
                raise RuntimeError("Le module gspread n'est pas installé.")
            if getattr(settings, "google_service_account_info", None) and settings.google_service_account_info.strip():
                raw_info = settings.google_service_account_info.strip()
                if raw_info.startswith("{"):
                    info_dict = json.loads(raw_info)
                else:
                    try:
                        decoded = base64.b64decode(raw_info).decode("utf-8")
                        info_dict = json.loads(decoded)
                    except Exception:
                        info_dict = json.loads(raw_info)
                gc = gspread.service_account_from_dict(info_dict)
            else:
                cred_file = credentials_path or settings.google_service_account_file
                gc = gspread.service_account(filename=cred_file)
            self._spreadsheet = gc.open_by_key(settings.spreadsheet_sport_id)

        self._sessions_cache: Optional[List[SportSession]] = None
        self._cache_time: float = 0.0
        self._cache_ttl_seconds: int = 180

    @property
    def name(self) -> str:
        return "sport_running"

    async def is_healthy(self) -> bool:
        """Vérifie si le classeur sport est accessible."""
        try:
            return bool(self._spreadsheet and self._get_seances_worksheet() is not None)
        except Exception:
            return False

    def invalidate_cache(self) -> None:
        """Invalide le cache mémoire des séances."""
        self._sessions_cache = None
        self._cache_time = 0.0

    def _get_seances_worksheet(self) -> Any:
        """Récupère l'onglet des séances en tolérant les accents et variantes."""
        available = [ws.title for ws in self._spreadsheet.worksheets()]
        resolved = resolve_worksheet(available, SEANCES_SHEET_ALIASES)
        if not resolved:
            raise ValueError(f"Onglet 'Séance' introuvable parmi : {available}")
        return self._spreadsheet.worksheet(resolved)

    def _get_synthese_worksheet(self) -> Optional[Any]:
        """Récupère l'onglet de synthèse hebdomadaire."""
        available = [ws.title for ws in self._spreadsheet.worksheets()]
        resolved = resolve_worksheet(available, SYNTHESE_SHEET_ALIASES)
        if not resolved:
            return None
        return self._spreadsheet.worksheet(resolved)

    def _get_all_sessions(self) -> List[SportSession]:
        """Charge et parse l'ensemble des séances de l'onglet."""
        ws = self._get_seances_worksheet()
        all_values = ws.get_all_values()
        if len(all_values) <= 1:
            return []

        headers = all_values[0]
        sessions: List[SportSession] = []

        header_indices = {h.strip().lower(): i for i, h in enumerate(headers)}

        def get_val(row: List[str], *aliases: str) -> Optional[str]:
            for a in aliases:
                idx = header_indices.get(a.lower())
                if idx is not None and idx < len(row):
                    return row[idx]
            return None

        for row in all_values[1:]:
            if not row or not any(row):
                continue
            date_raw = get_val(row, "Date")
            d = _parse_date_robust(date_raw)
            if not d:
                continue

            semaine = _safe_int(get_val(row, "Semaine")) or d.isocalendar()[1]
            statut_str = get_val(row, "Statut") or "Planifié"
            type_str = get_val(row, "Type de séance", "Type") or "EF"
            dist = _safe_float(get_val(row, "Distance (km)", "Distance"))
            d_plus = _safe_int(get_val(row, "Dénivelé D+ (m)", "Dénivelé", "D+")) or 0
            duree_sec = _parse_duration_seconds(get_val(row, "Temps", "Durée"))
            rpe = _safe_int(get_val(row, "ressenti dur/10", "Ressenti"))
            fc_moy = _safe_int(get_val(row, "FC Moy (bpm)", "FC Moy", "BPM Moy", "Fréquence Cardiaque"))
            fc_max = _safe_int(get_val(row, "FC Max (bpm)", "FC Max", "BPM Max"))
            meteo = _safe_int(get_val(row, "Météo difficile/10", "Météo"))
            note = get_val(row, "Note", "Notes") or ""
            strava_id = get_val(row, "ID Strava") or None

            statut_enum = SportSessionStatus.REALISE if "réalisé" in statut_str.lower() else SportSessionStatus.PLANIFIE
            try:
                type_enum = SportSessionType(type_str)
            except ValueError:
                type_enum = SportSessionType.EF

            session = SportSession(
                date=d,
                semaine=semaine,
                statut=statut_enum,
                type_seance=type_enum,
                distance_km=dist,
                denivele_d_plus=d_plus,
                duree_secondes=duree_sec,
                ressenti_rpe=rpe,
                fc_moyenne=fc_moy,
                fc_max=fc_max,
                meteo_note=meteo,
                notes=note,
                strava_id=strava_id,
            )
            sessions.append(session)

        return sessions

    def get_session(self, target_date: Optional[Union[date, str]] = None) -> Optional[SportSession]:
        """Récupère la séance planifiée ou réalisée pour une date cible."""
        if target_date is None:
            resolved_date = date.today()
        elif isinstance(target_date, str):
            resolved_date = parse_target_date(target_date)
        else:
            resolved_date = target_date

        sessions = self._get_all_sessions()
        for s in sessions:
            if s.date == resolved_date:
                return s
        return None

    def get_week_sessions(self, week_num: int, year: Optional[int] = None) -> List[SportSession]:
        """Récupère l'ensemble des séances d'une semaine ISO."""
        target_year = year or datetime.now().year
        sessions = self._get_all_sessions()
        return [s for s in sessions if s.semaine == week_num and s.date.year == target_year]

    def log_session(self, session_data: SportSessionCreate) -> SportSession:
        """Enregistre ou met à jour une séance terminée."""
        target_date = session_data.date or date.today()
        semaine_iso = target_date.isocalendar()[1]
        ws = self._get_seances_worksheet()
        all_values = ws.get_all_values()

        date_str = target_date.strftime("%d/%m/%Y")
        km_effort = calculate_km_effort(session_data.distance_km, session_data.denivele_d_plus)
        speed = calculate_speed_kmh(session_data.distance_km, session_data.duree_secondes)
        pace_sec = calculate_pace_min_km(session_data.distance_km, session_data.duree_secondes)
        pace_formatted = format_pace(pace_sec) or ""

        duration_formatted = ""
        if session_data.duree_secondes:
            h = session_data.duree_secondes // 3600
            m = (session_data.duree_secondes % 3600) // 60
            s = session_data.duree_secondes % 60
            duration_formatted = f"{h:02d}:{m:02d}:{s:02d}"

        # Chercher si une ligne existe déjà pour cette date
        existing_row_idx = None
        for i, row in enumerate(all_values[1:], start=2):
            if row and len(row) > 0 and _parse_date_robust(row[0]) == target_date:
                existing_row_idx = i
                break

        row_payload = [
            date_str,
            f'=IF(ISBLANK(A{existing_row_idx or len(all_values)+1}); ""; ISOWEEKNUM(A{existing_row_idx or len(all_values)+1}))',
            SportSessionStatus.REALISE.value,
            session_data.type_seance.value,
            session_data.distance_km,
            session_data.denivele_d_plus or 0,
            f'=IF(ISBLANK(E{existing_row_idx or len(all_values)+1}); ""; E{existing_row_idx or len(all_values)+1} + (IF(ISBLANK(F{existing_row_idx or len(all_values)+1}); 0; F{existing_row_idx or len(all_values)+1})/100))',
            duration_formatted,
            f'=IF(OR(ISBLANK(E{existing_row_idx or len(all_values)+1}); ISBLANK(H{existing_row_idx or len(all_values)+1}); H{existing_row_idx or len(all_values)+1}=0); ""; E{existing_row_idx or len(all_values)+1}/(H{existing_row_idx or len(all_values)+1}*24))',
            f'=IF(OR(ISBLANK(E{existing_row_idx or len(all_values)+1}); ISBLANK(H{existing_row_idx or len(all_values)+1}); E{existing_row_idx or len(all_values)+1}=0); ""; TEXT(H{existing_row_idx or len(all_values)+1}/E{existing_row_idx or len(all_values)+1}; "m\'ss") & """/km")',
            session_data.ressenti_rpe or "",
            f'=IF(OR(ISBLANK(H{existing_row_idx or len(all_values)+1}); ISBLANK(K{existing_row_idx or len(all_values)+1})); ""; (H{existing_row_idx or len(all_values)+1}*1440)*K{existing_row_idx or len(all_values)+1})',
            session_data.fc_moyenne or "",
            session_data.fc_max or "",
            session_data.meteo_note or "",
            session_data.notes or "",
            session_data.strava_id or "",
        ]

        if existing_row_idx:
            ws.update(range_name=f"A{existing_row_idx}:Q{existing_row_idx}", values=[row_payload], value_input_option="USER_ENTERED")
        else:
            if hasattr(ws, "append_row"):
                ws.append_row(row_payload, value_input_option="USER_ENTERED")
            else:
                next_row = len(all_values) + 1
                ws.update(range_name=f"A{next_row}:Q{next_row}", values=[row_payload], value_input_option="USER_ENTERED")

        self.invalidate_cache()

        return SportSession(
            date=target_date,
            semaine=semaine_iso,
            statut=SportSessionStatus.REALISE,
            type_seance=session_data.type_seance,
            distance_km=session_data.distance_km,
            denivele_d_plus=session_data.denivele_d_plus or 0,
            duree_secondes=session_data.duree_secondes,
            ressenti_rpe=session_data.ressenti_rpe,
            fc_moyenne=session_data.fc_moyenne,
            fc_max=session_data.fc_max,
            meteo_note=session_data.meteo_note,
            notes=session_data.notes,
            strava_id=session_data.strava_id,
        )

    def plan_session(self, plan_data: SportSessionPlan) -> SportSession:
        """Planifie une séance d'entraînement future."""
        target_date = plan_data.date
        semaine_iso = target_date.isocalendar()[1]
        ws = self._get_seances_worksheet()
        all_values = ws.get_all_values()
        date_str = target_date.strftime("%d/%m/%Y")

        row_payload = [
            date_str,
            f'=IF(ISBLANK(A{len(all_values)+1}); ""; ISOWEEKNUM(A{len(all_values)+1}))',
            SportSessionStatus.PLANIFIE.value,
            plan_data.type_seance.value,
            plan_data.distance_km_cible or "",
            0,
            f'=IF(ISBLANK(E{len(all_values)+1}); ""; E{len(all_values)+1} + (IF(ISBLANK(F{len(all_values)+1}); 0; F{len(all_values)+1})/100))',
            "", "", "", "", "", "", "", "",
            plan_data.notes or "",
            "",
        ]

        if hasattr(ws, "append_row"):
            ws.append_row(row_payload, value_input_option="USER_ENTERED")
        else:
            next_row = len(all_values) + 1
            ws.update(range_name=f"A{next_row}:Q{next_row}", values=[row_payload], value_input_option="USER_ENTERED")

        self.invalidate_cache()

        return SportSession(
            date=target_date,
            semaine=semaine_iso,
            statut=SportSessionStatus.PLANIFIE,
            type_seance=plan_data.type_seance,
            distance_km=plan_data.distance_km_cible,
            notes=plan_data.notes,
        )

    def get_weekly_summary(
        self,
        week_num: Optional[int] = None,
        year: Optional[int] = None,
        semaine: Optional[int] = None,
        annee: Optional[int] = None,
    ) -> SportWeeklySummary:
        """Récupère ou calcule la synthèse hebdomadaire et le diagnostic sécurité mini-coach."""
        target_week = week_num or semaine or datetime.now().isocalendar()[1]
        target_year = year or annee or datetime.now().year

        ws_syn = self._get_synthese_worksheet()
        if ws_syn:
            rows = ws_syn.get_all_values()
            for r in rows[1:]:
                if len(r) >= 6 and _safe_int(r[0]) == target_week and _safe_int(r[1]) == target_year:
                    km_tot = _safe_float(r[3]) or 0.0
                    d_plus_tot = _safe_int(r[4]) or 0
                    km_effort_tot = _safe_float(r[5]) or 0.0
                    duree_sec = _parse_duration_seconds(r[6]) or 0
                    nb_seances = _safe_int(r[2]) or 0

                    # Récupérer S-1
                    prev_km_effort = None
                    for prev_r in rows[1:]:
                        if len(prev_r) >= 6 and _safe_int(prev_r[0]) == target_week - 1 and _safe_int(prev_r[1]) == target_year:
                            prev_km_effort = _safe_float(prev_r[5])
                            break

                    return SportWeeklySummary(
                        semaine=target_week,
                        annee=target_year,
                        nb_seances=nb_seances,
                        km_total=km_tot,
                        d_plus_total=d_plus_tot,
                        km_effort_total=km_effort_tot,
                        duree_secondes=duree_sec,
                        previous_week_km_effort=prev_km_effort,
                    )

        # Si absent de Synthese_Hebdo, agrégation à la volée depuis Séance
        week_sessions = [s for s in self.get_week_sessions(target_week, target_year) if s.statut == SportSessionStatus.REALISE]
        nb_seances = len(week_sessions)
        km_total = sum(s.distance_km or 0.0 for s in week_sessions)
        d_plus_total = sum(s.denivele_d_plus or 0 for s in week_sessions)
        km_effort_total = sum(s.km_effort or 0.0 for s in week_sessions)
        duree_secondes = sum(s.duree_secondes or 0 for s in week_sessions)

        # Semaine précédente
        prev_sessions = [s for s in self.get_week_sessions(target_week - 1, target_year) if s.statut == SportSessionStatus.REALISE]
        prev_km_effort = sum(s.km_effort or 0.0 for s in prev_sessions) if prev_sessions else None

        return SportWeeklySummary(
            semaine=target_week,
            annee=target_year,
            nb_seances=nb_seances,
            km_total=round(km_total, 2),
            d_plus_total=d_plus_total,
            km_effort_total=round(km_effort_total, 2),
            duree_secondes=duree_secondes,
            previous_week_km_effort=prev_km_effort,
        )

    async def execute_action(self, action_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Exécute une action standardisée sur le connecteur sport."""
        if action_name == "get_session":
            target_date = parameters.get("target_date")
            session = self.get_session(target_date)
            return {
                "success": True,
                "found": session is not None,
                "session": session.model_dump(mode="json") if session else None,
            }

        elif action_name == "log_session":
            session_create = SportSessionCreate(**parameters)
            logged = self.log_session(session_create)
            return {
                "success": True,
                "session": logged.model_dump(mode="json"),
            }

        elif action_name == "plan_session":
            plan = SportSessionPlan(**parameters)
            planned = self.plan_session(plan)
            return {
                "success": True,
                "session": planned.model_dump(mode="json"),
            }

        elif action_name == "get_weekly_summary":
            week_num = parameters.get("week_num")
            year = parameters.get("year")
            summary = self.get_weekly_summary(week_num=week_num, year=year)
            return {
                "success": True,
                "found": True,
                "summary": summary.model_dump(mode="json"),
            }

        raise NotImplementedError(f"Action '{action_name}' non supportée par SportConnector.")
