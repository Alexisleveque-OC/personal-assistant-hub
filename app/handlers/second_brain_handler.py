"""Handler dédié au Second Cerveau compartimenté (capture, consultation, suppression de notes)."""
import logging
from typing import Any, Dict, Optional, Tuple

from app.core.models import IntentType, ParsedIntent, NoteCategory
from app.core.dependencies import get_database_manager

logger = logging.getLogger(__name__)

CATEGORY_LABELS_FR = {
    NoteCategory.DEV_IDEA.value: "tes idées dev",
    NoteCategory.BUG_REPORT.value: "tes bugs et corrections",
    NoteCategory.TASK.value: "tes tâches",
    NoteCategory.PREFERENCE.value: "tes préférences",
    NoteCategory.THOUGHT.value: "tes réflexions",
}


async def handle_second_brain_intent(
    parsed: ParsedIntent,
    raw_query: str,
    session_ctx: Dict[str, Any],
    data: Dict[str, Any],
) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Intercepte et exécute les intentions du Second Cerveau SQLite."""
    if parsed.intent not in (
        IntentType.SAVE_NOTE,
        IntentType.LIST_NOTES,
        IntentType.DELETE_NOTE,
    ):
        return None

    db = get_database_manager()

    match parsed.intent:
        case IntentType.SAVE_NOTE:
            content = parsed.parameters.get("content") or raw_query
            category = parsed.parameters.get("category") or NoteCategory.THOUGHT.value
            tags = parsed.parameters.get("tags") or []

            note_id = db.add_note(category=category, content=content, tags=tags)
            label = CATEGORY_LABELS_FR.get(category, f"tes notes « {category} »")

            spoken = f"C'est bien noté dans {label} : {content}."
            data.update({
                "note_id": note_id,
                "category": category,
                "content": content,
                "tags": tags,
            })
            session_ctx["last_undoable_action"] = {
                "type": "save_note",
                "note_id": note_id,
                "content": content,
                "category": category,
            }
            return spoken, data

        case IntentType.LIST_NOTES:
            category = parsed.parameters.get("category")
            res = db.get_notes(category=category, status="active", limit=5)
            total = res.get("total", 0)
            items = res.get("items", [])

            label = CATEGORY_LABELS_FR.get(category, f"tes notes « {category} »") if category else "tes notes"


            if total == 0:
                spoken = f"Tu n'as aucune note active dans {label}."
            else:
                summary_items = [f"« {item['content']} »" for item in items[:3]]
                summary_text = " ; ".join(summary_items)
                if total > 3:
                    summary_text += f" (et {total - 3} autre{'s' if total - 3 > 1 else ''})"
                spoken = f"Tu as {total} note{'s' if total > 1 else ''} dans {label} : {summary_text}."

            data.update({
                "total": total,
                "items": items,
                "category": category,
            })
            return spoken, data

        case IntentType.DELETE_NOTE:
            note_id = parsed.parameters.get("note_id")
            if not note_id:
                spoken = "Quelle note souhaites-tu supprimer ? Merci de préciser son identifiant."
                data["error"] = "missing_note_id"
                return spoken, data

            deleted = db.delete_note(int(note_id))
            if deleted:
                spoken = f"La note {note_id} a bien été supprimée."
            else:
                spoken = f"Impossible de supprimer la note {note_id} : elle n'existe pas."

            data.update({"note_id": note_id, "deleted": deleted})
            return spoken, data

    return None
