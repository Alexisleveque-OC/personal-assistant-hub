"""Handler dédié au traitement des intentions sport, running et coach Otis."""
from datetime import date, timedelta
import logging
from typing import Any, Dict, Optional, Tuple

from app.core.models import IntentType, ParsedIntent
from app.connectors.sheets.sport_connector import SportConnector
from app.connectors.sheets.sport_models import (
    SportSession,
    SportSessionCreate,
    SportSessionPlan,
    SportSessionStatus,
    SportSessionType,
    SportSessionUpdate,
)
from app.core.date_resolver import parse_target_date
from app.core.sport_coach_service import SportCoachService

logger = logging.getLogger(__name__)


async def handle_sport_intent(
    parsed: ParsedIntent,
    raw_query: str,
    session_ctx: Dict[str, Any],
    sport_connector: Optional[SportConnector],
    data: Dict[str, Any],
) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Exécute l'intention si elle concerne le module sport.

    Retourne (spoken_response, data) si gérée, ou None si l'intention n'est pas sportive.
    """
    match parsed.intent:
        case IntentType.GET_SPORT_SESSION:
            is_last = (
                parsed.parameters.get("last_session") is True
                or parsed.parameters.get("target_date") in ("last", "derniere", "dernière")
            )
            requested_type = parsed.parameters.get("session_type") or parsed.parameters.get("type_seance")

            if is_last:
                if not sport_connector:
                    return "Le carnet d'entraînement sport n'est pas configuré.", data

                if hasattr(sport_connector, "get_last_session"):
                    session = sport_connector.get_last_session(session_type=requested_type)
                else:
                    all_s = [s for s in sport_connector.get_all_sessions() if s.statut == SportSessionStatus.REALISE]
                    if requested_type:
                        all_s = [s for s in all_s if str(s.type_seance).lower() == str(requested_type).lower()]
                    all_s.sort(key=lambda s: s.date, reverse=True)
                    session = all_s[0] if all_s else None

                if session:
                    data["session"] = session.model_dump(mode="json")
                    type_nom = session.type_seance.value if hasattr(session.type_seance, "value") else str(session.type_seance)
                    dist_str = f"{session.distance_km:.2f}".rstrip("0").rstrip(".").replace(".", ",") if session.distance_km else ""
                    spoken = f"Votre dernière séance était une séance de {type_nom}"
                    if dist_str:
                        spoken += f" de {dist_str} km"
                    details = session.programme or session.notes
                    if details:
                        spoken += f" : {details}"
                    if session.remarques and session.remarques != details:
                        spoken += f" (Remarques : {session.remarques})"
                    spoken += "."
                else:
                    label = f" de type {requested_type}" if requested_type else ""
                    spoken = f"Aucune séance précédente{label} n'a été trouvée dans votre historique."
                return spoken, data

            target_date_raw = parsed.parameters.get("target_date")
            if isinstance(target_date_raw, date):
                target_d = target_date_raw
            elif target_date_raw in ("today", "aujourd'hui", None):
                target_d = date.today()
            elif target_date_raw == "demain":
                target_d = date.today() + timedelta(days=1)
            elif target_date_raw == "hier":
                target_d = date.today() - timedelta(days=1)
            else:
                target_d = parse_target_date(str(target_date_raw))

            if sport_connector:
                session = sport_connector.get_session(target_d)
                if session:
                    data["session"] = session.model_dump()
                    type_nom = session.type_seance.value if hasattr(session.type_seance, "value") else str(session.type_seance)
                    dist_str = f"{session.distance_km:.2f}".rstrip("0").rstrip(".").replace(".", ",") if session.distance_km else ""
                    spoken = f"Pour aujourd'hui, vous avez une séance de {type_nom}"
                    if dist_str:
                        spoken += f" de {dist_str} km"
                    details = session.programme or session.notes
                    if details:
                        spoken += f" : {details}"
                    if session.remarques and session.remarques != details:
                        spoken += f" (Remarques : {session.remarques})"
                    spoken += "."
                else:
                    spoken = "Aucune séance n'est planifiée pour cette date. C'est une journée de repos bien méritée !"
            else:
                spoken = "Le carnet d'entraînement sport n'est pas configuré."
            return spoken, data

        case IntentType.LOG_SPORT_SESSION:
            raw_dist = parsed.parameters.get("distance_km")
            dist = float(raw_dist) if raw_dist is not None else None
            dur_sec = parsed.parameters.get("duration_seconds")
            if not dur_sec and "duree_minutes" in parsed.parameters:
                dur_sec = int(parsed.parameters["duree_minutes"]) * 60
            d_plus = int(parsed.parameters.get("denivele_d_plus", 0))
            rpe = parsed.parameters.get("ressenti_rpe")
            raw_date = parsed.parameters.get("target_date")
            if isinstance(raw_date, date):
                session_date = raw_date
            elif raw_date:
                session_date = parse_target_date(str(raw_date))
            else:
                session_date = date.today()

            type_seance_param = parsed.parameters.get("type_seance")
            if isinstance(type_seance_param, str):
                if type_seance_param.lower() in ("renfo", "renforcement", "ppg", "musculation"):
                    type_seance = SportSessionType.RENFORCEMENT
                else:
                    try:
                        type_seance = SportSessionType(type_seance_param)
                    except ValueError:
                        type_seance = SportSessionType.EF
            elif isinstance(type_seance_param, SportSessionType):
                type_seance = type_seance_param
            else:
                type_seance = SportSessionType.EF

            prog = parsed.parameters.get("programme")
            rem = parsed.parameters.get("remarques")
            notes = parsed.parameters.get("notes", "")

            # Récupération de la séance planifiée du jour si confirmation
            is_validating_planned = bool(parsed.parameters.get("validate_planned"))
            planned_session = None
            if sport_connector and (is_validating_planned or (dist is None and not dur_sec and type_seance == SportSessionType.EF)):
                try:
                    candidate = sport_connector.get_session(session_date)
                    if candidate and candidate.statut == SportSessionStatus.PLANIFIE:
                        planned_session = candidate
                except Exception:
                    planned_session = None

            if planned_session:
                if "type_seance" not in parsed.parameters and planned_session.type_seance:
                    type_seance = planned_session.type_seance
                if dist is None and planned_session.distance_km and type_seance != SportSessionType.RENFORCEMENT:
                    dist = planned_session.distance_km
                if not dur_sec and planned_session.duree_secondes:
                    dur_sec = planned_session.duree_secondes
                if not prog and planned_session.programme:
                    prog = planned_session.programme

            if not prog and notes and type_seance == SportSessionType.RENFORCEMENT:
                prog = notes
            elif not rem and notes:
                rem = notes

            session_create = SportSessionCreate(
                date=session_date,
                type_seance=type_seance,
                distance_km=dist,
                duree_secondes=dur_sec or 1800,
                denivele_d_plus=d_plus,
                ressenti_rpe=rpe,
                programme=prog or "",
                remarques=rem or "",
                notes=notes,
            )

            new_session = None
            if sport_connector:
                try:
                    new_session = sport_connector.log_session(session_create)
                except Exception as exc:
                    logger.warning(f"Erreur enregistrement séance sport : {exc}")

            if not new_session:
                new_session = SportSession(
                    date=session_date,
                    semaine=session_date.isocalendar()[1],
                    statut=SportSessionStatus.REALISE,
                    type_seance=type_seance,
                    distance_km=dist,
                    duree_secondes=dur_sec or 1800,
                    denivele_d_plus=d_plus,
                    ressenti_rpe=rpe,
                    programme=prog or "",
                    remarques=rem or "",
                    notes=notes,
                )

            data["session"] = new_session.model_dump()
            minutes = ((dur_sec or 1800) // 60)
            if is_validating_planned and planned_session:
                dist_str = f" de {str(dist).replace('.', ',')} km" if dist else ""
                spoken = f"Super ! J'ai validé votre séance prévue ({new_session.type_seance.value}{dist_str}) comme Réalisée dans votre carnet."
                if rpe:
                    spoken += f" Ressenti noté à {rpe}/10."
                else:
                    spoken += " Quel était votre ressenti sur 10 ?"
            elif type_seance == SportSessionType.RENFORCEMENT or dist is None:
                charge_txt = f" (charge RPE de {new_session.charge_rpe})" if new_session.charge_rpe else ""
                spoken = f"C'est enregistré ! Votre séance de renforcement musculaire de {minutes} minutes{charge_txt} a bien été ajoutée au carnet."
            else:
                dist_disp = str(dist).replace(".", ",")
                allure = new_session.allure_formatted or ""
                spoken = f"C'est enregistré ! Votre séance de {dist_disp} km en {minutes} minutes"
                if allure:
                    spoken += f" (allure {allure}/km)"
                spoken += " a bien été enregistrée dans votre carnet."
            return spoken, data

        case IntentType.UPDATE_SPORT_SESSION:
            raw_date = parsed.parameters.get("target_date")
            if isinstance(raw_date, date):
                target_d = raw_date
            elif raw_date in ("today", "aujourd'hui", None):
                target_d = date.today()
            elif raw_date == "demain":
                target_d = date.today() + timedelta(days=1)
            elif raw_date == "hier":
                target_d = date.today() - timedelta(days=1)
            elif raw_date:
                target_d = parse_target_date(str(raw_date))
            else:
                target_d = date.today()

            rpe = parsed.parameters.get("ressenti_rpe")
            prog = parsed.parameters.get("programme")
            rem = parsed.parameters.get("remarques")
            notes = parsed.parameters.get("notes")
            append_rem = parsed.parameters.get("append_remarques", parsed.parameters.get("append_notes", True))

            if sport_connector:
                update_payload = SportSessionUpdate(
                    ressenti_rpe=rpe,
                    programme=prog,
                    remarques=rem,
                    notes=notes,
                    append_remarques=append_rem,
                    append_notes=append_rem,
                )
                try:
                    updated = sport_connector.update_session(target_d, update_payload)
                    data["session"] = updated.model_dump()
                    date_disp = target_d.strftime("%d/%m")
                    charge = updated.charge_rpe

                    spoken_parts = [f"C'est noté Alexis. J'ai mis à jour ta séance du {date_disp}"]
                    if rpe is not None:
                        spoken_parts.append(f"avec un ressenti de {rpe}/10")
                        if charge:
                            spoken_parts.append(f"(charge réévaluée à {charge})")
                    elif rem or notes:
                        spoken_parts.append(f"avec la note : {rem or notes}")
                    elif prog:
                        spoken_parts.append(f"avec le programme : {prog}")
                    spoken = " ".join(spoken_parts) + "."

                    # Prévention périostite / blessure
                    feedback_text = (rem or notes or "").lower()
                    if "périostite" in feedback_text or "tibia" in feedback_text or "douleur" in feedback_text or (rpe and rpe >= 8):
                        spoken += " Attention à ta périostite : applique du froid, masse la zone et privilégie le repos et les sols souples."
                    else:
                        spoken += " Pense à bien récupérer !"
                except Exception as exc:
                    logger.warning(f"Erreur mise à jour séance sport : {exc}")
                    spoken = f"Désolé Alexis, je n'ai pas pu modifier la séance : {exc}"
            else:
                spoken = "Le carnet d'entraînement sport n'est pas configuré."
            return spoken, data

        case IntentType.GET_SPORT_WEEKLY_SUMMARY:
            sem = parsed.parameters.get("semaine")
            an = parsed.parameters.get("annee")
            if not sem or not an:
                iso_cal = date.today().isocalendar()
                sem = sem or iso_cal[1]
                an = an or iso_cal[0]

            if sport_connector:
                summary = sport_connector.get_weekly_summary(semaine=int(sem), annee=int(an))
                if summary:
                    data["summary"] = summary.model_dump()
                    km_effort_disp = str(summary.km_effort_total).replace(".", ",")
                    spoken = f"Cette semaine, vous totalisez {summary.nb_seances} séances pour un total de {km_effort_disp} km-effort."
                    if summary.plafond_conseille_s_plus_1:
                        max_next = str(summary.plafond_conseille_s_plus_1).replace(".", ",")
                        spoken += f" En respectant la règle des 10%, je vous conseille de ne pas dépasser {max_next} km-effort la semaine prochaine."
                    elif summary.alerte_securite:
                        spoken += f" Conseil coach : {summary.alerte_securite}"
                else:
                    spoken = "Aucune donnée de course enregistrée pour cette semaine."
            else:
                spoken = "Le carnet d'entraînement sport n'est pas configuré."
            return spoken, data

        case IntentType.PLAN_SPORT_SESSION:
            t_date_raw = parsed.parameters.get("target_date")
            day_name = parsed.parameters.get("day_name")
            if isinstance(t_date_raw, date):
                t_date = t_date_raw
            elif t_date_raw or day_name:
                t_date = parse_target_date(t_date_raw or day_name)
            else:
                t_date = date.today() + timedelta(days=1)

            t_type = parsed.parameters.get("type_seance", "EF")
            dist = parsed.parameters.get("distance_km")
            notes = parsed.parameters.get("notes")

            if sport_connector:
                planned = sport_connector.plan_session(
                    session_date=t_date,
                    type_seance=t_type,
                    distance_km=dist,
                    notes=notes,
                )
                data["session"] = planned.model_dump()
            date_disp = t_date.strftime("%d/%m/%Y")
            spoken = f"C'est noté ! J'ai planifié une séance de {t_type} pour le {date_disp}."
            return spoken, data

        case IntentType.PLAN_WEEKLY_TRAINING:
            if not sport_connector:
                spoken = "Le carnet d'entraînement sport n'est pas configuré."
            else:
                coach_service = SportCoachService(connector=sport_connector)
                try:
                    target_w = parsed.parameters.get("semaine") or parsed.parameters.get("week_num")
                    target_y = parsed.parameters.get("annee") or parsed.parameters.get("year")
                    plan_proposal = await coach_service.plan_weekly_training(
                        query=raw_query,
                        target_week=int(target_w) if target_w else None,
                        target_year=int(target_y) if target_y else None,
                    )
                    data["weekly_plan"] = plan_proposal.model_dump()

                    # Insertion groupée des séances planifiées
                    plan_items = [
                        SportSessionPlan(
                            date=s_prop.date_seance,
                            type_seance=s_prop.type_seance,
                            distance_km_cible=s_prop.distance_km,
                            allure_cible=s_prop.allure_cible,
                            vitesse_cible=s_prop.vitesse_cible,
                            programme=s_prop.programme or "",
                            remarques=s_prop.remarques_coach or "",
                        )
                        for s_prop in plan_proposal.seances
                        if s_prop.date_seance
                    ]
                    inserted_objs = sport_connector.plan_weekly_sessions(plan_items)
                    data["inserted_sessions"] = [s.model_dump() for s in inserted_objs]

                    spoken = plan_proposal.spoken_summary
                    if inserted_objs:
                        spoken += f" J'ai inséré les {len(inserted_objs)} séances prévues dans votre carnet d'entraînement."
                except Exception as exc:
                    logger.error(f"Erreur génération plan hebdomadaire sport : {exc}")
                    spoken = f"Impossible de générer votre plan d'entraînement : {exc}"
            return spoken, data

        case IntentType.EXPLAIN_SPORT_EXERCISE:
            ex_target = parsed.parameters.get("exercise", raw_query)
            coach_service = SportCoachService(connector=sport_connector) if sport_connector else SportCoachService(connector=None)
            spoken = coach_service.explain_exercise(ex_target)
            data["exercise"] = ex_target
            data["explanation"] = spoken
            return spoken, data

        case _:
            return None
