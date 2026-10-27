"""Réponse directe après une modification simple : évite le 2e appel Gemini (≈ moitié de la latence d'un tour).

Décision du 27/10/2026 : séance modifiée, enregistrée ou planifiée ; articles ajoutés, cochés ou retirés ; note
enregistrée. Gemini garde la main pour tout le reste : lectures, plan de la semaine, repas, erreurs, rayon à
demander, et demandes composées (une 2e action enchaînée serait perdue si la boucle s'arrêtait).
"""
import re
from datetime import date
from typing import Any, Callable, Dict, List, Optional, Sequence

from app.core.agent.tool_registry import ToolExecution

_COMPOSITE_WORDS = re.compile(r"\b(?:et|puis|aussi|ensuite)\b", re.IGNORECASE)

_SESSION_LABELS = {
    "EF": "footing", "Fractionné": "fractionné", "Sortie Longue": "sortie longue", "Course": "course",
    "Vitesse": "séance de vitesse", "Tempo": "tempo", "Récup": "footing de récup", "Renforcement": "renfo",
}
_FEMININE_LABELS = frozenset({"sortie longue", "course", "séance de vitesse", "renfo"})
_NOTE_LABELS = {
    "dev_idea": "idées de dev", "bug_report": "bugs", "thought": "réflexions", "preference": "préférences",
    "task": "tâches",
}


def fast_reply(query: str, executions: Sequence[ToolExecution]) -> Optional[str]:
    """Phrase de confirmation si le tour ne contient que des modifications simples réussies ; None sinon."""
    if not executions or _COMPOSITE_WORDS.search(query):
        return None
    phrases = []
    for execution in executions:
        build = _BUILDERS.get(execution.name)
        phrase = build(execution) if build and execution.error is None else None
        if phrase is None:
            return None
        phrases.append(phrase)
    return " ".join(phrases)


def _join(names: Sequence[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} et {names[-1]}"


def _duration(seconds: int) -> str:
    hours, minutes = divmod(round(seconds / 60), 60)
    return f"{hours} h {minutes:02d}" if hours else f"{minutes} min"


def _day(session: Dict[str, Any]) -> str:
    return f"{session['jour']} {date.fromisoformat(session['date']).strftime('%d/%m')}"


def _label(session_type: str) -> str:
    return _SESSION_LABELS.get(session_type, session_type)


def _your(session_type: str) -> str:
    label = _label(session_type)
    return f"{'ta' if label in _FEMININE_LABELS else 'ton'} {label}"


def _details(values: Dict[str, Any]) -> List[str]:
    """Valeurs dites par l'utilisateur, dans un ordre de lecture naturel."""
    formats: Dict[str, Callable[[Any], str]] = {
        "duree_secondes": _duration,
        "distance_km": lambda v: f"{v:g} km",
        "denivele_d_plus": lambda v: f"{v} m D+",
        "ressenti_rpe": lambda v: f"RPE {v}",
        "fc_moyenne": lambda v: f"FC moyenne {v}",
        "fc_max": lambda v: f"FC max {v}",
        "meteo_note": lambda v: f"météo {v}/10",
        "type_seance": lambda v: f"type {_label(v)}",
        "statut": lambda v: f"statut {v}",
        "date": lambda v: f"date {date.fromisoformat(str(v)).strftime('%d/%m')}",
        "allure_cible": lambda v: f"allure {v}",
        "vitesse_cible": lambda v: f"vitesse {v}",
        "programme": lambda v: "programme mis à jour",
        "remarques": lambda v: "remarque ajoutée",
    }
    return [fmt(values[key]) for key, fmt in formats.items() if values.get(key) is not None]


def _updated(execution: ToolExecution) -> Optional[str]:
    session = execution.response["session"]
    changes = _details(execution.args.get("changes", {}))
    if not changes:
        return None
    return f"C'est noté : {', '.join(changes)} pour {_your(session['type_seance'])} du {_day(session)}."


def _logged(execution: ToolExecution) -> Optional[str]:
    session = execution.response["session"]
    details = _details({k: v for k, v in execution.args.items() if k not in ("date", "type_seance")})
    return f"C'est enregistré : {_label(session['type_seance'])} du {_day(session)}{''.join(', ' + d for d in details)}."


def _planned(execution: ToolExecution) -> Optional[str]:
    session = execution.response["session"]
    details = _details({k: v for k, v in execution.args.items() if k not in ("date", "type_seance")})
    return f"C'est planifié : {_label(session['type_seance'])} le {_day(session)}{''.join(', ' + d for d in details)}."


def _added(execution: ToolExecution) -> Optional[str]:
    response = execution.response
    names = [article["nom"] for article in response.get("ajoutes", [])]
    if response.get("rayon_a_demander") or not names:
        return None
    return f"J'ai ajouté {_join(names)} à la liste de courses."


def _checked(execution: ToolExecution) -> Optional[str]:
    response = execution.response
    names = response.get("modifies", []) + response.get("deja_dans_cet_etat", [])
    if response.get("introuvables") or not names:
        return None
    return f"C'est {'coché' if response.get('coche', True) else 'décoché'} : {', '.join(names)}."


def _removed(execution: ToolExecution) -> Optional[str]:
    response = execution.response
    if response.get("introuvables") or response.get("remarque") or not response.get("retires"):
        return None
    return f"J'ai retiré {_join(response['retires'])} de la liste de courses."


def _note(execution: ToolExecution) -> Optional[str]:
    label = _NOTE_LABELS.get(execution.response.get("category"))
    return f"C'est noté dans tes {label}." if label else None


_BUILDERS: Dict[str, Callable[[ToolExecution], Optional[str]]] = {
    "update_sport_session": _updated,
    "log_sport_session": _logged,
    "plan_sport_session": _planned,
    "add_shopping_items": _added,
    "check_shopping_items": _checked,
    "remove_shopping_items": _removed,
    "save_note": _note,
}
