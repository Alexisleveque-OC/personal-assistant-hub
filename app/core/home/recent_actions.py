"""« Dernières actions » de l'accueil : les modifications faites par Otis, lues dans le journal des conversations.

Les simples lectures (« donne-moi la liste ») et les échecs sont ignorés ; chaque action reçoit un libellé court.
Seule la plus récente peut être annulée, et seulement depuis la session qui l'a faite : le serveur n'annule
que la dernière action d'une session (« annule ça »)."""
import json
import logging
from datetime import date
from typing import Any, Callable, Dict, Iterable, List, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

WEEKDAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
UNDO_INTENT = "undo_last_action"


class RecentAction(BaseModel):
    id: int
    label: str
    created_at: Optional[str] = None  # ISO 8601 en UTC (« …Z »)
    undoable: bool = False


class RecentActionsResponse(BaseModel):
    items: List[RecentAction]


def _names(names: List[str]) -> str:
    """« A », « A et B », « A, B et C », « A, B et 3 autres »."""
    if len(names) <= 1:
        return "".join(names)
    if len(names) <= 3:
        return f"{', '.join(names[:-1])} et {names[-1]}"
    return f"{names[0]}, {names[1]} et {len(names) - 2} autres"



def _items_label(names: List[str], verb: str, suffix: str) -> Optional[str]:
    names = [n for n in names if n]
    if not names:
        return None
    plural = len(names) > 1
    return f"{_names(names)} {verb}{'s' if plural else ''} {suffix}"


def _weekday(raw: Any) -> Optional[str]:
    try:
        return WEEKDAYS_FR[date.fromisoformat(str(raw)[:10]).weekday()]
    except (TypeError, ValueError):
        return None


def _km(raw: Any) -> str:
    if raw in (None, "", 0):
        return ""
    return f" · {float(raw):.2f}".rstrip("0").rstrip(".").replace(".", ",") + " km"


def _session_label(day: Any, verb: str, distance: Any = None) -> str:
    weekday = _weekday(day)
    base = f"Séance du {weekday} {verb}" if weekday else f"Séance {verb}"
    return base + _km(distance)


# Outils de l'agent qui modifient des données → libellé (à partir de leurs arguments).
_TOOL_LABELS: Dict[str, Callable[[Dict[str, Any]], Optional[str]]] = {
    "add_shopping_items": lambda a: _items_label([x.get("nom", "") for x in a.get("articles", [])], "ajouté", "aux courses"),
    "remove_shopping_items": lambda a: _items_label(a.get("noms", []), "retiré", "des courses"),
    "check_shopping_items": lambda a: _items_label(
        a.get("noms", []), "coché" if a.get("coche", True) else "décoché", "dans les courses"),
    "clear_bought_shopping_items": lambda a: "Articles achetés retirés des courses",
    "add_task": lambda a: f"Tâche ajoutée : {a['titre']}" if a.get("titre") else "Tâche ajoutée",
    "complete_task": lambda a: "Tâche terminée",
    "save_note": lambda a: "Note ajoutée au Second cerveau",
    "set_meal": lambda a: f"Repas prévu : {a['plat']}" if a.get("plat") else "Repas prévu",
    "log_sport_session": lambda a: _session_label(a.get("date"), "enregistrée", a.get("distance_km")),
    "plan_sport_session": lambda a: _session_label(a.get("date"), "planifiée"),
    "update_sport_session": lambda a: "Séance modifiée",
    "plan_weekly_training": lambda a: "Semaine d'entraînement planifiée",
    "undo_last_action": lambda a: "Dernière action annulée",
}


def _added_articles(p: Dict[str, Any]) -> Optional[str]:
    """Articles réellement ajoutés : le journal garde des objets pour les ajouts, et de simples chaînes
    quand Otis demande d'abord le rayon (« rayon_question » : rien n'est encore dans la liste)."""
    names = [x.get("item", "") for x in p.get("items") or [] if isinstance(x, dict)]
    return _items_label(names, "ajouté", "aux courses")


def _session(p: Dict[str, Any]) -> Dict[str, Any]:
    return p.get("session") or {}


# Intentions historiques (flux regex / NLU) qui modifient des données → libellé (à partir des paramètres journalisés).
_INTENT_LABELS: Dict[str, Callable[[Dict[str, Any]], Optional[str]]] = {
    "add_shopping_item": _added_articles,
    "choose_rayon": _added_articles,  # réponse à « dans quel rayon ? » : l'article est ajouté à ce moment-là
    "add_recipe_ingredients": lambda p: "Ingrédients ajoutés aux courses",
    "mark_shopping_bought": lambda p: "Articles cochés dans les courses",
    "clear_shopping_list": lambda p: "Articles achetés retirés des courses",
    "set_meal_plan": lambda p: "Repas prévu",
    "add_task": lambda p: f"Tâche ajoutée : {p['titre']}" if p.get("titre") else "Tâche ajoutée",
    "save_note": lambda p: "Note ajoutée au Second cerveau",
    "delete_note": lambda p: "Note supprimée",
    "log_sport_session": lambda p: _session_label(_session(p).get("date"), "enregistrée", _session(p).get("distance_km")),
    "plan_sport_session": lambda p: _session_label(_session(p).get("date"), "planifiée"),
    "update_sport_session": lambda p: "Séance modifiée",
    "fix_sport_duplicate": lambda p: "Doublon de séance corrigé",
    "plan_weekly_training": lambda p: "Semaine d'entraînement planifiée",
    "teach_assistant": lambda p: "Correction mémorisée",
    "log_expense": lambda p: "Dépense enregistrée",
    UNDO_INTENT: lambda p: "Dernière action annulée",
}


def _parameters(log: Dict[str, Any]) -> Dict[str, Any]:
    raw = log.get("parameters") or {}
    if isinstance(raw, str):
        raw = json.loads(raw) if raw.strip() else {}
    return raw if isinstance(raw, dict) else {}


def _is_undo(log: Dict[str, Any]) -> bool:
    if log.get("intent") == UNDO_INTENT:
        return True
    calls = _parameters(log).get("tool_calls") or []
    return any(c.get("name") == UNDO_INTENT and not c.get("error") for c in calls)


def action_label(log: Dict[str, Any]) -> Optional[str]:
    """Libellé court de l'action journalisée, ou None si l'échange n'a rien modifié."""
    params = _parameters(log)
    if log.get("intent") == "agent":
        labels = [
            _TOOL_LABELS[c["name"]](c.get("args") or {})
            for c in params.get("tool_calls") or []
            if c.get("name") in _TOOL_LABELS and not c.get("error")
        ]
        labels = [l for l in labels if l]
        return " · ".join(labels) if labels else None
    builder = _INTENT_LABELS.get(log.get("intent", ""))
    return builder(params) if builder else None


def _iso_utc(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    text = str(raw).replace(" ", "T")
    return text if text.endswith("Z") or "+" in text[10:] else f"{text}Z"


def recent_actions(logs: Iterable[Dict[str, Any]], session_id: Optional[str], limit: int = 3) -> List[RecentAction]:
    """`logs` : journal du plus récent au plus ancien."""
    items: List[RecentAction] = []
    for log in logs:
        if not log.get("success"):
            continue
        try:
            label = action_label(log)
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            # Une entrée au format inattendu ne doit pas vider l'accueil : elle est signalée et sautée.
            logger.warning(f"Dernières actions : journal n°{log.get('id')} ({log.get('intent')}) illisible, ignoré : {exc!r}")
            continue
        if not label:
            continue
        undoable = not items and bool(session_id) and log.get("session_id") == session_id and not _is_undo(log)
        items.append(RecentAction(id=log["id"], label=label, created_at=_iso_utc(log.get("created_at")), undoable=undoable))
        if len(items) >= limit:
            break
    return items
