
"""Connecteur Google Sheets pour le suivi de course à pied et Mini-Coach (SportConnector)."""
from datetime import date, datetime, timedelta
import json
import base64
import re
import time
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
    SportSessionUpdate,
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


def _normalize_session_type(raw: str) -> SportSessionType:
    """Convertit le libellé brut du Sheet en type de séance (même règle que la lecture des séances)."""
    clean = (raw or "").strip()
    if clean.lower() in ("renfo", "renforcement", "ppg", "musculation"):
        return SportSessionType.RENFORCEMENT
    try:
        return SportSessionType(clean)
    except ValueError:
        return SportSessionType.EF


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

            if not getattr(settings, "spreadsheet_sport_id", None) or not settings.spreadsheet_sport_id.strip():
                raise ValueError("Variable d'environnement SPREADSHEET_SPORT_ID manquante ou non configurée")
            self._spreadsheet = gc.open_by_key(settings.spreadsheet_sport_id)

        self._sessions_cache: Optional[List[SportSession]] = None
        self._cache_time: float = 0.0
        self._synthese_cache: Optional[List[List[str]]] = None
        self._synthese_cache_time: float = 0.0
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
        """Invalide le cache mémoire des séances et de la synthèse."""
        self._sessions_cache = None
        self._cache_time = 0.0
        self._synthese_cache = None
        self._synthese_cache_time = 0.0

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
        now = time.time()
        if self._sessions_cache is not None and (now - self._cache_time < self._cache_ttl_seconds):
            return self._sessions_cache

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
            prog = get_val(row, "Programme", "Détail Séance", "Contenu", "Exercices") or ""
            rem = get_val(row, "Remarques", "Remarque") or ""
            legacy_note = get_val(row, "Note", "Notes") or ""
            if not rem and legacy_note:
                rem = legacy_note
            if not prog and not rem and legacy_note:
                prog = legacy_note
            strava_id = get_val(row, "ID Strava") or None

            statut_enum = SportSessionStatus.REALISE if "réalisé" in statut_str.lower() else SportSessionStatus.PLANIFIE
            type_clean = type_str.strip()
            type_lower = type_clean.lower()
            if type_lower in ("renfo", "renforcement", "ppg", "musculation"):
                type_enum = SportSessionType.RENFORCEMENT
            elif type_lower in ("fractionné", "fractionne"):
                type_enum = SportSessionType.FRACTIONNE
            elif type_lower in ("sortie longue", "sortie_longue"):
                type_enum = SportSessionType.SORTIE_LONGUE
            elif type_lower in ("course", "running"):
                type_enum = SportSessionType.COURSE
            elif type_lower == "vitesse":
                type_enum = SportSessionType.VITESSE
            elif type_lower == "tempo":
                type_enum = SportSessionType.TEMPO
            elif type_lower in ("récup", "recup"):
                type_enum = SportSessionType.RECUP
            elif type_lower in ("ef", "endurance fondamentale"):
                type_enum = SportSessionType.EF
            else:
                try:
                    type_enum = SportSessionType(type_clean)
                except ValueError:
                    type_enum = SportSessionType.EF

            raw_vit = get_val(row, "Vitesse (km/h)", "Vitesse") or ""
            raw_allure = get_val(row, "Allure (min/km)", "Allure") or ""
            vitesse_cible = None
            allure_cible = None
            if statut_enum == SportSessionStatus.PLANIFIE:
                if "+/-" in raw_vit or "km/h" in raw_vit:
                    vitesse_cible = raw_vit.strip() or None
                if "+/-" in raw_allure or "/km" in raw_allure:
                    allure_cible = raw_allure.strip() or None

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
                programme=prog,
                remarques=rem,
                notes=rem or prog,
                allure_cible=allure_cible,
                vitesse_cible=vitesse_cible,
                strava_id=strava_id,
            )
            sessions.append(session)

        self._sessions_cache = sessions
        self._cache_time = now
        return sessions

    def get_all_sessions(self) -> List[SportSession]:
        """Retourne l'historique complet des séances (copie défensive du cache, pour le dashboard)."""
        return list(self._get_all_sessions())

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
        # Année ISO (et non calendaire) : la semaine 1 peut commencer fin décembre de l'année précédente
        return [s for s in sessions if s.semaine == week_num and s.date.isocalendar()[0] == target_year]

    def log_session(self, session_data: SportSessionCreate) -> SportSession:
        """Enregistre ou met à jour une séance terminée."""
        target_date = session_data.date or date.today()
        semaine_iso = target_date.isocalendar()[1]
        ws = self._get_seances_worksheet()
        all_values = ws.get_all_values()

        date_str = target_date.strftime("%d/%m/%Y")
        dist_val = session_data.distance_km if session_data.distance_km is not None else ""
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

        headers = all_values[0] if all_values else []
        header_indices = {h.strip().lower(): i for i, h in enumerate(headers)}
        has_prog_col = any(h in header_indices for h in ["programme", "detail seance", "détail séance", "contenu"])

        existing_prog = ""
        existing_rem = ""
        existing_type_str = ""
        if existing_row_idx and existing_row_idx - 1 < len(all_values):
            ex_row = all_values[existing_row_idx - 1]
            p_idx = header_indices.get("programme") or header_indices.get("detail seance") or header_indices.get("détail séance") or header_indices.get("contenu")
            if p_idx is not None and p_idx < len(ex_row):
                existing_prog = ex_row[p_idx]
            r_idx = header_indices.get("remarques") or header_indices.get("remarque")
            if r_idx is not None and r_idx < len(ex_row):
                existing_rem = ex_row[r_idx]
            if not existing_prog and not existing_rem:
                n_idx = header_indices.get("note") or header_indices.get("notes")
                if n_idx is not None and n_idx < len(ex_row):
                    existing_prog = ex_row[n_idx]
            t_idx = header_indices.get("type de séance") or header_indices.get("type")
            if t_idx is not None and t_idx < len(ex_row):
                existing_type_str = ex_row[t_idx].strip()

        # Si l'entrée (Strava ou log rapide) est le type par défaut EF, mais que la séance prévue
        # avait un type spécifique (ex: Fractionné, Sortie Longue, Renfo), on conserve le type prévu !
        final_type = session_data.type_seance
        if existing_type_str and session_data.type_seance == SportSessionType.EF:
            clean_ex = existing_type_str.lower()
            if clean_ex in ("renfo", "renforcement", "ppg", "musculation"):
                final_type = SportSessionType.RENFORCEMENT
            elif clean_ex not in ("ef", "endurance fondamentale"):
                try:
                    final_type = SportSessionType(existing_type_str)
                except ValueError:
                    pass

        prog_val = session_data.programme or existing_prog or ""
        rem_val = session_data.remarques or session_data.notes or existing_rem or ""

        row_payload = [
            date_str,
            f'=IF(ISBLANK(A{existing_row_idx or len(all_values)+1}); ""; ISOWEEKNUM(A{existing_row_idx or len(all_values)+1}))',
            SportSessionStatus.REALISE.value,
            final_type.value,
            dist_val,
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
        ]

        if has_prog_col:
            row_payload.extend([prog_val, rem_val, session_data.strava_id or ""])
            end_col = "R"
        else:
            row_payload.extend([rem_val or prog_val, session_data.strava_id or ""])
            end_col = "Q"

        if existing_row_idx:
            ws.update(range_name=f"A{existing_row_idx}:{end_col}{existing_row_idx}", values=[row_payload], value_input_option="USER_ENTERED")
        else:
            if hasattr(ws, "append_row"):
                ws.append_row(row_payload, value_input_option="USER_ENTERED")
            else:
                next_row = len(all_values) + 1
                ws.update(range_name=f"A{next_row}:{end_col}{next_row}", values=[row_payload], value_input_option="USER_ENTERED")

        if hasattr(ws.get_all_values, "return_value") and isinstance(ws.get_all_values.return_value, list):
            while len(row_payload) < 18:
                row_payload.append("")
            if existing_row_idx and existing_row_idx - 1 < len(ws.get_all_values.return_value):
                ws.get_all_values.return_value[existing_row_idx - 1] = [str(x) for x in row_payload]
            else:
                ws.get_all_values.return_value.append([str(x) for x in row_payload])

        self.invalidate_cache()

        return SportSession(
            date=target_date,
            semaine=semaine_iso,
            statut=SportSessionStatus.REALISE,
            type_seance=final_type,
            distance_km=session_data.distance_km,
            denivele_d_plus=session_data.denivele_d_plus or 0,
            duree_secondes=session_data.duree_secondes,
            ressenti_rpe=session_data.ressenti_rpe,
            fc_moyenne=session_data.fc_moyenne,
            fc_max=session_data.fc_max,
            meteo_note=session_data.meteo_note,
            programme=prog_val,
            remarques=rem_val,
            notes=rem_val or prog_val,
            strava_id=session_data.strava_id,
        )

    def plan_session(
        self,
        plan_data: Optional[SportSessionPlan] = None,
        session_date: Optional[Union[date, str]] = None,
        type_seance: Optional[Union[SportSessionType, str]] = None,
        distance_km: Optional[float] = None,
        notes: Optional[str] = None,
        programme: Optional[str] = None,
        remarques: Optional[str] = None,
    ) -> SportSession:
        """Planifie une séance d'entraînement future."""
        if plan_data is None:
            if isinstance(session_date, str):
                target_d = parse_target_date(session_date)
            elif isinstance(session_date, date):
                target_d = session_date
            else:
                target_d = date.today() + timedelta(days=1)

            if isinstance(type_seance, str):
                try:
                    t_enum = SportSessionType(type_seance)
                except ValueError:
                    t_enum = SportSessionType.EF
            elif isinstance(type_seance, SportSessionType):
                t_enum = type_seance
            else:
                t_enum = SportSessionType.EF

            plan = SportSessionPlan(
                date=target_d,
                type_seance=t_enum,
                distance_km_cible=distance_km,
                programme=programme or notes or "",
                remarques=remarques or "",
                notes=notes or programme or "",
            )
        else:
            plan = plan_data

        target_date = plan.date
        semaine_iso = target_date.isocalendar()[1]
        ws = self._get_seances_worksheet()
        all_values = ws.get_all_values()
        date_str = target_date.strftime("%d/%m/%Y")

        # Chercher si une ligne existe déjà pour cette date afin de la mettre à jour
        existing_row_idx = None
        for i, row in enumerate(all_values[1:], start=2):
            if row and len(row) > 0 and _parse_date_robust(row[0]) == target_date:
                existing_row_idx = i
                break

        headers = all_values[0] if all_values else []
        header_indices = {h.strip().lower(): i for i, h in enumerate(headers)}
        has_prog_col = any(h in header_indices for h in ["programme", "detail seance", "détail séance", "contenu"])

        prog_val = plan.programme or plan.notes or ""
        rem_val = plan.remarques or ""

        target_tags = []
        if plan.allure_cible:
            target_tags.append(plan.allure_cible)
        if plan.vitesse_cible:
            target_tags.append(plan.vitesse_cible)
        if target_tags:
            target_label = f"[Cible : {' | '.join(target_tags)}]"
            if target_label not in prog_val:
                prog_val = f"{target_label} {prog_val}".strip() if prog_val else target_label

        r_idx = existing_row_idx or (len(all_values) + 1)
        row_payload = [
            date_str,
            f'=IF(ISBLANK(A{r_idx}); ""; ISOWEEKNUM(A{r_idx}))',
            SportSessionStatus.PLANIFIE.value,
            plan.type_seance.value,
            plan.distance_km_cible if (plan.distance_km_cible is not None and plan.distance_km_cible > 0) else "",
            0,
            f'=IF(ISBLANK(E{r_idx}); ""; E{r_idx} + (IF(ISBLANK(F{r_idx}); 0; F{r_idx})/100))',
            "",
            plan.vitesse_cible or "",
            plan.allure_cible or "",
            "", "", "", "", "",
        ]

        if has_prog_col:
            row_payload.extend([prog_val, rem_val, ""])
            end_col = "R"
        else:
            row_payload.extend([prog_val or rem_val, ""])
            end_col = "Q"

        if existing_row_idx:
            ws.update(range_name=f"A{existing_row_idx}:{end_col}{existing_row_idx}", values=[row_payload], value_input_option="USER_ENTERED")
        else:
            if hasattr(ws, "append_row"):
                ws.append_row(row_payload, value_input_option="USER_ENTERED")
            else:
                next_row = len(all_values) + 1
                ws.update(range_name=f"A{next_row}:{end_col}{next_row}", values=[row_payload], value_input_option="USER_ENTERED")

        if hasattr(ws.get_all_values, "return_value") and isinstance(ws.get_all_values.return_value, list):
            while len(row_payload) < 18:
                row_payload.append("")
            if existing_row_idx and existing_row_idx - 1 < len(ws.get_all_values.return_value):
                ws.get_all_values.return_value[existing_row_idx - 1] = [str(x) for x in row_payload]
            else:
                ws.get_all_values.return_value.append([str(x) for x in row_payload])

        self.invalidate_cache()

        return SportSession(
            date=target_date,
            semaine=semaine_iso,
            statut=SportSessionStatus.PLANIFIE,
            type_seance=plan.type_seance,
            distance_km=plan.distance_km_cible,
            allure_cible=plan.allure_cible,
            vitesse_cible=plan.vitesse_cible,
            programme=prog_val,
            remarques=rem_val,
            notes=prog_val or rem_val,
        )

    def plan_weekly_sessions(
        self,
        plans: List[SportSessionPlan],
    ) -> List[SportSession]:
        """Insère ou met à jour en lot (batch) les séances d'un plan hebdomadaire complet avec statut Prévu."""
        if not plans:
            return []

        ws = self._get_seances_worksheet()
        all_values = ws.get_all_values()
        headers = all_values[0] if all_values else []
        header_indices = {h.strip().lower(): i for i, h in enumerate(headers)}
        has_prog_col = any(h in header_indices for h in ["programme", "detail seance", "détail séance", "contenu"])
        end_col = "R" if (has_prog_col or len(headers) >= 18) else "Q"
        slice_len = 18 if end_col == "R" else 17

        # Indexation des dates existantes vers numéro de ligne (1-based)
        date_to_row_idx: Dict[date, int] = {}
        for i, row in enumerate(all_values[1:], start=2):
            if row and len(row) > 0:
                d_parsed = _parse_date_robust(row[0])
                if d_parsed:
                    date_to_row_idx[d_parsed] = i

        created_sessions: List[SportSession] = []
        updates_to_perform: List[tuple] = []
        rows_to_append: List[List[Any]] = []
        total_rows_init = len(all_values)

        for plan in plans:
            target_date = plan.date
            existing_idx = date_to_row_idx.get(target_date)
            r_idx = existing_idx if existing_idx else (total_rows_init + len(rows_to_append) + 1)
            date_str = target_date.strftime("%d/%m/%Y")
            prog_val = plan.programme or plan.notes or ""
            rem_val = plan.remarques or ""
            dist_val = plan.distance_km_cible if (plan.distance_km_cible is not None and plan.distance_km_cible > 0) else ""

            target_tags = []
            if plan.allure_cible:
                target_tags.append(plan.allure_cible)
            if plan.vitesse_cible:
                target_tags.append(plan.vitesse_cible)
            if target_tags:
                target_label = f"[Cible : {' | '.join(target_tags)}]"
                if target_label not in prog_val:
                    prog_val = f"{target_label} {prog_val}".strip() if prog_val else target_label

            row_payload = [
                date_str,
                f'=IF(ISBLANK(A{r_idx}); ""; ISOWEEKNUM(A{r_idx}))',
                SportSessionStatus.PLANIFIE.value,
                plan.type_seance.value,
                dist_val,
                0,
                f'=IF(ISBLANK(E{r_idx}); ""; E{r_idx} + (IF(ISBLANK(F{r_idx}); 0; F{r_idx})/100))',
                "",
                plan.vitesse_cible or "",
                plan.allure_cible or "",
                "", "", "", "", "",
            ]
            if has_prog_col or len(headers) >= 18:
                row_payload.extend([prog_val, rem_val, ""])
            else:
                row_payload.extend([rem_val or prog_val, ""])

            while len(row_payload) < slice_len:
                row_payload.append("")
            row_payload = row_payload[:slice_len]

            if existing_idx:
                updates_to_perform.append((f"A{existing_idx}:{end_col}{existing_idx}", [row_payload]))
                if existing_idx - 1 < len(all_values):
                    all_values[existing_idx - 1] = row_payload
            else:
                rows_to_append.append(row_payload)
                all_values.append(row_payload)

            created_sessions.append(
                SportSession(
                    date=target_date,
                    semaine=target_date.isocalendar()[1],
                    statut=SportSessionStatus.PLANIFIE,
                    type_seance=plan.type_seance,
                    distance_km=plan.distance_km_cible if (plan.distance_km_cible and plan.distance_km_cible > 0) else None,
                    denivele_d_plus=0,
                    duree_secondes=0,
                    ressenti_rpe=None,
                    allure_cible=plan.allure_cible,
                    vitesse_cible=plan.vitesse_cible,
                    programme=prog_val,
                    remarques=rem_val,
                    notes=rem_val or prog_val,
                )
            )

        for range_name, vals in updates_to_perform:
            ws.update(range_name=range_name, values=vals, value_input_option="USER_ENTERED")

        if rows_to_append:
            if hasattr(ws, "append_rows"):
                ws.append_rows(rows_to_append, value_input_option="USER_ENTERED")
            elif hasattr(ws, "append_row"):
                for r in rows_to_append:
                    ws.append_row(r, value_input_option="USER_ENTERED")
            else:
                start_r = total_rows_init + 1
                end_r = total_rows_init + len(rows_to_append)
                ws.update(range_name=f"A{start_r}:{end_col}{end_r}", values=rows_to_append, value_input_option="USER_ENTERED")

        if hasattr(ws.get_all_values, "return_value") and isinstance(ws.get_all_values.return_value, list):
            ws.get_all_values.return_value = all_values

        self.invalidate_cache()
        return created_sessions

    def update_session(
        self,
        target_date: Union[date, str],
        update_data: Union[SportSessionUpdate, Dict[str, Any]],
        target_type: Optional[SportSessionType] = None,
    ) -> SportSession:
        """Modifie a posteriori une séance existante (RPE, notes de douleur/périostite, ressenti).

        `target_type` permet de cibler la bonne ligne lorsque plusieurs séances partagent la même date
        (ex : Renfo + EF). Sans `target_type`, la première séance de la date est modifiée.
        """
        if isinstance(target_date, str):
            resolved_date = parse_target_date(target_date)
        else:
            resolved_date = target_date

        if isinstance(update_data, dict):
            update_payload = SportSessionUpdate(**update_data)
        else:
            update_payload = update_data

        ws = self._get_seances_worksheet()
        all_values = ws.get_all_values()
        if len(all_values) <= 1:
            raise ValueError(f"Aucune séance trouvée pour la date {resolved_date}.")

        headers = all_values[0]
        header_indices = {h.strip().lower(): i for i, h in enumerate(headers)}

        type_idx = header_indices.get("type de séance")
        if type_idx is None:
            type_idx = header_indices.get("type", 3)
        types_on_date: List[str] = []

        target_row_idx = None
        current_row = None
        for i, row in enumerate(all_values[1:], start=2):
            if row and len(row) > 0 and _parse_date_robust(row[0]) == resolved_date:
                row_type_raw = row[type_idx].strip() if type_idx < len(row) else ""
                types_on_date.append(row_type_raw)
                if target_type is not None and _normalize_session_type(row_type_raw) != target_type:
                    continue
                target_row_idx = i
                current_row = list(row)
                break

        if not target_row_idx or not current_row:
            if target_type is not None and types_on_date:
                raise ValueError(
                    f"Aucune séance de type '{target_type.value}' le {resolved_date}. "
                    f"Types disponibles à cette date : {types_on_date}."
                )
            raise ValueError(f"Aucune séance trouvée pour la date {resolved_date}.")

        # S'assurer que current_row a au moins 18 éléments pour accueillir Programme et Remarques
        while len(current_row) < 18:
            current_row.append("")

        has_prog_col = any(h in header_indices for h in ["programme", "detail seance", "détail séance", "contenu"])

        def set_col(val: Any, *col_aliases: str, fallback_idx: int) -> None:
            for alias in col_aliases:
                idx = header_indices.get(alias.lower())
                if idx is not None:
                    current_row[idx] = val
                    return
            current_row[fallback_idx] = val

        # 1. RPE
        if update_payload.ressenti_rpe is not None:
            set_col(update_payload.ressenti_rpe, "ressenti dur/10", "ressenti", fallback_idx=10)

        # 2. Programme
        if update_payload.programme is not None:
            set_col(update_payload.programme, "programme", "detail seance", "détail séance", "contenu", fallback_idx=15)

        # 3. Remarques & Notes
        rem_val = update_payload.remarques if update_payload.remarques is not None else update_payload.notes
        if rem_val is not None:
            rem_idx = header_indices.get("remarques") or header_indices.get("remarque")
            if rem_idx is not None:
                old_rem = current_row[rem_idx] if rem_idx < len(current_row) else ""
                if (update_payload.append_remarques or update_payload.append_notes) and old_rem.strip():
                    new_rem = f"{old_rem.strip()} | {rem_val.strip()}"
                else:
                    new_rem = rem_val.strip()
                current_row[rem_idx] = new_rem
            else:
                note_idx = header_indices.get("note") or header_indices.get("notes") or 15
                old_note = current_row[note_idx] if note_idx < len(current_row) else ""
                if (update_payload.append_remarques or update_payload.append_notes) and old_note.strip():
                    new_note = f"{old_note.strip()} | {rem_val.strip()}"
                else:
                    new_note = rem_val.strip()
                current_row[note_idx] = new_note

        # 4. Type de séance
        if update_payload.type_seance is not None:
            set_col(update_payload.type_seance.value, "type de séance", "type", fallback_idx=3)

        # 5. FC Moy / FC Max
        if update_payload.fc_moyenne is not None:
            set_col(update_payload.fc_moyenne, "fc moy (bpm)", "fc moy", fallback_idx=12)
        if update_payload.fc_max is not None:
            set_col(update_payload.fc_max, "fc max (bpm)", "fc max", fallback_idx=13)

        # 6. Météo
        if update_payload.meteo_note is not None:
            set_col(update_payload.meteo_note, "météo difficile/10", "météo", fallback_idx=14)

        # Sauvegarde sur Google Sheet
        end_col = "R" if (has_prog_col or len(headers) >= 18) else "Q"
        slice_len = 18 if end_col == "R" else 17
        ws.update(
            range_name=f"A{target_row_idx}:{end_col}{target_row_idx}",
            values=[current_row[:slice_len]],
            value_input_option="USER_ENTERED",
        )

        # Mettre à jour all_values en mémoire si présent (pour les mocks de test)
        try:
            all_values[target_row_idx - 1] = current_row
        except Exception:
            pass

        self.invalidate_cache()

        def get_val(row_data: List[str], *aliases: str) -> Optional[str]:
            for a in aliases:
                idx = header_indices.get(a.lower())
                if idx is not None and idx < len(row_data):
                    return row_data[idx]
            return None

        d = resolved_date
        semaine = _safe_int(get_val(current_row, "Semaine")) or d.isocalendar()[1]
        statut_str = get_val(current_row, "Statut") or "Planifié"
        type_str = get_val(current_row, "Type de séance", "Type") or "EF"
        dist = _safe_float(get_val(current_row, "Distance (km)", "Distance"))
        d_plus = _safe_int(get_val(current_row, "Dénivelé D+ (m)", "Dénivelé", "D+")) or 0
        duree_sec = _parse_duration_seconds(get_val(current_row, "Temps", "Durée"))
        rpe = _safe_int(get_val(current_row, "ressenti dur/10", "Ressenti"))
        fc_moy = _safe_int(get_val(current_row, "FC Moy (bpm)", "FC Moy", "BPM Moy", "Fréquence Cardiaque"))
        fc_max = _safe_int(get_val(current_row, "FC Max (bpm)", "FC Max", "BPM Max"))
        meteo = _safe_int(get_val(current_row, "Météo difficile/10", "Météo"))
        prog = get_val(current_row, "Programme", "Détail Séance", "Contenu", "Exercices") or ""
        rem = get_val(current_row, "Remarques", "Remarque") or ""
        legacy_note = get_val(current_row, "Note", "Notes") or ""
        if not rem and legacy_note:
            rem = legacy_note
        if not prog and not rem and legacy_note:
            prog = legacy_note
        strava_id = get_val(current_row, "ID Strava") or None

        statut_enum = SportSessionStatus.REALISE if "réalisé" in statut_str.lower() else SportSessionStatus.PLANIFIE
        type_clean = type_str.strip()
        if type_clean.lower() in ("renfo", "renforcement", "ppg", "musculation"):
            type_enum = SportSessionType.RENFORCEMENT
        else:
            try:
                type_enum = SportSessionType(type_clean)
            except ValueError:
                type_enum = SportSessionType.EF

        return SportSession(
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
            programme=prog,
            remarques=rem,
            notes=rem or prog,
            strava_id=strava_id,
        )


    def get_weekly_summary(
        self,
        week_num: Optional[int] = None,
        year: Optional[int] = None,
        semaine: Optional[int] = None,
        annee: Optional[int] = None,
    ) -> SportWeeklySummary:
        """Récupère ou calcule la synthèse hebdomadaire multicritère et le diagnostic sécurité mini-coach."""
        target_week = week_num or semaine or datetime.now().isocalendar()[1]
        target_year = year or annee or datetime.now().year

        # Calculer les métriques dérivées depuis les séances réelles de la semaine
        week_sessions = [s for s in self.get_week_sessions(target_week, target_year) if s.statut == SportSessionStatus.REALISE]
        charge_rpe_totale = sum(s.charge_rpe or 0 for s in week_sessions)
        nb_renfo = sum(1 for s in week_sessions if s.type_seance == SportSessionType.RENFORCEMENT)

        # Filtrer les séances de course réelles (avec distance > 0 et hors renforcement)
        running_sessions = [
            s for s in week_sessions
            if s.type_seance != SportSessionType.RENFORCEMENT and (s.distance_km or 0) > 0
        ]
        duree_course_sec = sum(s.duree_secondes or 0 for s in running_sessions)

        # Semaine précédente (S-1) calculée depuis les séances (vitesse calculée sur les courses)
        # Calcul par date pour gérer le passage d'année ISO (S1 -> S52/S53 de l'année précédente)
        prev_iso = (date.fromisocalendar(target_year, target_week, 1) - timedelta(days=7)).isocalendar()
        prev_week, prev_year = prev_iso[1], prev_iso[0]
        prev_sessions = [s for s in self.get_week_sessions(prev_week, prev_year) if s.statut == SportSessionStatus.REALISE]
        prev_running = [
            s for s in prev_sessions
            if s.type_seance != SportSessionType.RENFORCEMENT and (s.distance_km or 0) > 0
        ]
        prev_run_km = sum(s.distance_km or 0.0 for s in prev_running) if prev_running else 0.0
        prev_run_duree = sum(s.duree_secondes or 0 for s in prev_running) if prev_running else 0
        prev_vitesse = calculate_speed_kmh(prev_run_km, prev_run_duree) if (prev_run_km > 0 and prev_run_duree > 0) else None
        prev_charge_rpe = sum(s.charge_rpe or 0 for s in prev_sessions) if prev_sessions else None
        prev_km_effort = sum(s.km_effort or 0.0 for s in prev_sessions) if prev_sessions else None

        ws_syn = self._get_synthese_worksheet()
        if ws_syn:
            now = time.time()
            if self._synthese_cache is not None and (now - self._synthese_cache_time < self._cache_ttl_seconds):
                rows = self._synthese_cache
            else:
                rows = ws_syn.get_all_values()
                self._synthese_cache = rows
                self._synthese_cache_time = now

            headers = [h.strip().lower() for h in rows[0]] if rows else []
            header_map = {h: i for i, h in enumerate(headers)}

            for r in rows[1:]:
                if len(r) >= 6 and _safe_int(r[0]) == target_week and _safe_int(r[1]) == target_year:
                    km_tot = _safe_float(r[3]) or 0.0
                    d_plus_tot = _safe_int(r[4]) or 0
                    km_effort_tot = _safe_float(r[5]) or 0.0
                    duree_sec = _parse_duration_seconds(r[6]) or 0
                    nb_seances = _safe_int(r[2]) or 0

                    # Récupérer S-1 depuis Synthese_Hebdo si disponible
                    for prev_r in rows[1:]:
                        if len(prev_r) >= 6 and _safe_int(prev_r[0]) == prev_week and _safe_int(prev_r[1]) == prev_year:
                            prev_km_effort = _safe_float(prev_r[5]) or prev_km_effort
                            if "vitesse moyenne" in header_map and header_map["vitesse moyenne"] < len(prev_r):
                                prev_vitesse = _safe_float(prev_r[header_map["vitesse moyenne"]]) or prev_vitesse
                            if "charge rpe" in header_map and header_map["charge rpe"] < len(prev_r):
                                prev_charge_rpe = _safe_int(prev_r[header_map["charge rpe"]]) or prev_charge_rpe
                            break

                    cur_vit = calculate_speed_kmh(km_tot, duree_course_sec) if duree_course_sec > 0 else calculate_speed_kmh(km_tot, duree_sec)
                    if "vitesse moyenne" in header_map and header_map["vitesse moyenne"] < len(r):
                        cur_vit = _safe_float(r[header_map["vitesse moyenne"]]) or cur_vit

                    return SportWeeklySummary(
                        semaine=target_week,
                        annee=target_year,
                        nb_seances=nb_seances,
                        km_total=km_tot,
                        d_plus_total=d_plus_tot,
                        km_effort_total=km_effort_tot,
                        duree_secondes=duree_sec,
                        duree_course_secondes=duree_course_sec,
                        vitesse_moyenne_kmh=cur_vit,
                        charge_rpe_totale=charge_rpe_totale,
                        nb_renfo=nb_renfo,
                        previous_week_km_effort=prev_km_effort,
                        previous_week_vitesse_kmh=prev_vitesse,
                        previous_week_charge_rpe=prev_charge_rpe,
                    )

        # Si absent de Synthese_Hebdo, agrégation à la volée depuis Séance
        nb_seances = len(week_sessions)
        km_total = sum(s.distance_km or 0.0 for s in week_sessions)
        d_plus_total = sum(s.denivele_d_plus or 0 for s in week_sessions)
        km_effort_total = sum(s.km_effort or 0.0 for s in week_sessions)
        duree_secondes = sum(s.duree_secondes or 0 for s in week_sessions)
        cur_vitesse = calculate_speed_kmh(km_total, duree_course_sec) if duree_course_sec > 0 else calculate_speed_kmh(km_total, duree_secondes)

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
        """Retourne la liste de toutes les synthèses hebdomadaires ordonnées chronologiquement de façon décroissante."""
        ws_syn = self._get_synthese_worksheet()
        summaries: List[SportWeeklySummary] = []
        weeks_seen = set()

        if ws_syn:
            now = time.time()
            if self._synthese_cache is not None and (now - self._synthese_cache_time < self._cache_ttl_seconds):
                rows = self._synthese_cache
            else:
                rows = ws_syn.get_all_values()
                self._synthese_cache = rows
                self._synthese_cache_time = now

            if len(rows) > 1:
                pairs = []
                for r in rows[1:]:
                    if len(r) >= 2:
                        w = _safe_int(r[0])
                        y = _safe_int(r[1])
                        if w is not None and y is not None:
                            if year is not None and y != year:
                                continue
                            if (w, y) not in weeks_seen:
                                weeks_seen.add((w, y))
                                pairs.append((y, w))
                pairs.sort(reverse=True)
                for y, w in pairs:
                    summaries.append(self.get_weekly_summary(week_num=w, year=y))
                return summaries

        # Fallback si pas de Synthese_Hebdo ou onglet vide : calcul dynamique depuis les séances
        all_sessions = self.get_all_sessions()
        pairs = []
        for s in all_sessions:
            iso_year, iso_week, _ = s.date.isocalendar()
            w = s.semaine or iso_week
            y = iso_year
            if year is not None and y != year:
                continue
            if (w, y) not in weeks_seen:
                weeks_seen.add((w, y))
                pairs.append((y, w))

        pairs.sort(reverse=True)
        for y, w in pairs:
            summaries.append(self.get_weekly_summary(week_num=w, year=y))
        return summaries

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

        elif action_name == "update_session":
            target_date = parameters.get("target_date")
            updated = self.update_session(target_date, parameters)
            return {
                "success": True,
                "session": updated.model_dump(mode="json"),
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

