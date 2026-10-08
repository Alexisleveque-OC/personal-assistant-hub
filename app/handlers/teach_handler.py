"""Handler dédié à l'auto-apprentissage vocal et aux corrections d'Otis (user_learnings)."""
import logging
from typing import Any, Dict, Optional, Tuple

from app.core.models import IntentType, ParsedIntent
from app.core.dependencies import get_database_manager

logger = logging.getLogger(__name__)


async def handle_teach_intent(
    parsed: ParsedIntent,
    raw_query: str,
    session_ctx: Dict[str, Any],
    data: Dict[str, Any],
    session_id: Optional[str] = None,
) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Intercepte et exécute les intentions d'apprentissage et de correction vocale."""
    if parsed.intent != IntentType.TEACH_ASSISTANT:
        return None

    db = get_database_manager()

    original_error = parsed.parameters.get("original_error")
    correction = parsed.parameters.get("correction")
    category = parsed.parameters.get("category", "vocal_correction" if original_error else "custom_rule")
    rule_text = parsed.parameters.get("rule_text")

    if not rule_text:
        if original_error and correction:
            rule_text = f"Quand Alexis dit '{original_error}', comprendre '{correction}'"
        else:
            rule_text = raw_query.strip()

    # 1. Enregistrement de la règle dans la base SQLite
    learning_id = db.add_learning(
        rule_text=rule_text,
        category=category,
        original_error=original_error,
        correction=correction,
        active=True,
    )

    # 2. Rétro-correction et rattachement de feedback au tour précédent si existant
    target_session = session_id or session_ctx.get("session_id")
    if target_session:
        try:
            logs_res = db.get_conversation_logs(limit=1, session_id=target_session)
            items = logs_res.get("items", [])
            if items:
                prev_log_id = items[0]["id"]
                feedback_note = (
                    f"Correction vocale : '{original_error}' -> '{correction}'"
                    if original_error and correction
                    else f"Consigne enregistrée : {rule_text}"
                )
                db.add_feedback(
                    log_id=prev_log_id,
                    feedback_type="correction",
                    user_note=feedback_note,
                )
        except Exception as exc:
            logger.warning(f"Impossible de rattacher le feedback au log précédent: {exc}")

    # 3. Réponse orale bienveillante et complice
    if original_error and correction:
        spoken = f"C'est bien noté Alexis, j'ai retenu la correction : quand tu dis '{original_error}', je comprends '{correction}'."
    else:
        spoken = f"C'est bien noté et retenu, Alexis : {rule_text}."

    data.update({
        "learning_id": learning_id,
        "rule_text": rule_text,
        "original_error": original_error,
        "correction": correction,
        "category": category,
    })

    return spoken, data
