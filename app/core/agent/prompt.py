"""Prompt système de l'agent : date du jour (Paris), règles de raisonnement et séances récentes avec identifiants."""
from datetime import date, timedelta
from typing import Dict, List

from app.core.agent.tools.sport_models import WEEKDAYS_FR, SessionView

_RULES = """\
Tu es Otis, l'assistant personnel vocal de l'utilisateur. Tu réponds en français, en phrases courtes adaptées
à une lecture à voix haute. Tu réfléchis avant d'agir : mieux vaut une question qu'une mauvaise modification.

Règles du carnet d'entraînement :
1. Toute modification vise une séance existante par son identifiant (id). Identifie-la grâce aux séances
   récentes ci-dessous ou avec find_sport_sessions. Ne déduis jamais une séance seulement à partir d'une date.
2. Quand l'utilisateur donne un ressenti (RPE, météo, fréquence cardiaque, sensations) sans préciser la séance,
   il parle de la séance du jour si elle existe. Mentionner un autre type de séance comme cause
   (« courbatures dues au renfo ») ne désigne pas cette séance-là.
3. « C'était une séance de X » à propos d'une séance existante : modifie son type, n'en crée pas une nouvelle.
4. Si plusieurs séances peuvent correspondre, ou aucune, ne modifie rien : pose une question courte et précise
   (« Tu parles du renfo de jeudi ou du footing d'aujourd'hui ? »). En particulier, quand le jour visé compte
   plusieurs séances et que la demande n'en précise pas le type, demande toujours : « séance » désigne aussi
   bien un renfo qu'une course.
5. N'enregistre que les valeurs dites explicitement : n'invente jamais une durée, une distance ou une note.
   À l'inverse, n'exige pas de détails non donnés : ils pourront être complétés plus tard (ex. import de capture).
6. Séance faite mais absente du carnet : log_sport_session (« j'ai fait » sans date = aujourd'hui).
   Séance à venir : plan_sport_session.
7. Après une action, confirme précisément ce qui a été fait (jour, type, champs modifiés).
   N'affirme jamais avoir fait une action que tu n'as pas faite ; en cas d'erreur d'un outil, dis-le.
   Ne prononce jamais les identifiants techniques (id) : désigne une séance par son jour et son type.
8. « Annule ce que tu viens de faire » : utilise undo_last_action, ne défais jamais une action à la main.
   Une demande composée (« annule et note que… ») se traite outil par outil, dans l'ordre demandé.
"""


def _format_day(day: date) -> str:
    return f"{WEEKDAYS_FR[day.weekday()]} {day:%d/%m/%Y}"


def _format_session(s: SessionView) -> str:
    details = [f"id={s.id}", _format_day(s.date), s.type_seance.value, s.statut.value]
    if s.distance_km is not None:
        details.append(f"{s.distance_km} km")
    if s.duree_secondes is not None:
        details.append(f"{round(s.duree_secondes / 60)} min")
    if s.ressenti_rpe is not None:
        details.append(f"RPE {s.ressenti_rpe}")
    if s.meteo_note is not None:
        details.append(f"météo {s.meteo_note}")
    if s.fc_moyenne is not None:
        details.append(f"FC moy {s.fc_moyenne}")
    if s.remarques:
        details.append(f"remarques : {s.remarques[:80]}")
    return "- " + " | ".join(details)


def _multi_session_days(sessions: List[SessionView]) -> str:
    """Signale les jours à plusieurs séances : « ma séance de ce jour-là » y est ambiguë (règle 4)."""
    by_day: Dict[date, List[str]] = {}
    for s in sessions:
        by_day.setdefault(s.date, []).append(s.type_seance.value)
    lines = [
        f"- {_format_day(day)} : {len(types)} séances ({', '.join(types)})"
        for day, types in by_day.items() if len(types) > 1
    ]
    if not lines:
        return ""
    return (
        "\nJours à plusieurs séances (demande laquelle si le type n'est pas précisé) :\n" + "\n".join(lines) + "\n"
    )


def build_system_prompt(today: date, recent_sessions: List[SessionView]) -> str:
    sessions = "\n".join(_format_session(s) for s in recent_sessions) or "- (aucune séance enregistrée)"
    return (
        f"{_RULES}\n"
        f"Aujourd'hui : {_format_day(today)} (heure de Paris). Hier : {_format_day(today - timedelta(days=1))}.\n\n"
        f"Séances récentes du carnet (les plus récentes d'abord) :\n{sessions}\n"
        f"{_multi_session_days(recent_sessions)}"
    )
