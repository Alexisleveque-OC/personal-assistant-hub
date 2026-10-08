"""Handler dédié à l'annulation immédiate de la dernière action réversible ('Undo')."""
import logging
from typing import Any, Dict, Optional, Tuple

from app.core.models import IntentType, ParsedIntent
from app.core.dependencies import get_database_manager

logger = logging.getLogger(__name__)


async def handle_undo_intent(
    parsed: ParsedIntent,
    raw_query: str,
    session_ctx: Dict[str, Any],
    data: Dict[str, Any],
    connector: Optional[Any] = None,
    sport_connector: Optional[Any] = None,
) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Intercepte et exécute l'inversion contextuelle de la dernière action réversible."""
    if parsed.intent != IntentType.UNDO_LAST_ACTION:
        return None

    last_action = session_ctx.pop("last_undoable_action", None)
    if not last_action:
        return "Il n'y a aucune action récente à annuler.", data

    db = get_database_manager()
    action_type = last_action.get("type")

    match action_type:
        case "save_note":
            note_id = last_action.get("note_id")
            content = last_action.get("content", "")
            if note_id:
                db.delete_note(note_id)
            spoken = f"J'ai bien annulé l'enregistrement de ta note : {content}."
            data["undone_action"] = last_action
            return spoken, data

        case "teach_assistant":
            learning_id = last_action.get("learning_id")
            rule_text = last_action.get("rule_text", "")
            if learning_id:
                db.delete_learning(learning_id)
            spoken = f"J'ai bien annulé cette règle d'apprentissage : {rule_text}."
            data["undone_action"] = last_action
            return spoken, data

        case "add_shopping_item":
            items = last_action.get("items", [])
            if connector and hasattr(connector, "remove_shopping_item"):
                for item in items:
                    try:
                        connector.remove_shopping_item(item)
                    except Exception as exc:
                        logger.warning(f"Erreur lors du retrait de l'article {item}: {exc}")
            items_str = ", ".join(items) if items else "l'article"
            spoken = f"J'ai bien annulé l'ajout de {items_str} aux courses."
            data["undone_action"] = last_action
            return spoken, data

        case _:
            spoken = "L'opération précédente a bien été annulée."
            data["undone_action"] = last_action
            return spoken, data
