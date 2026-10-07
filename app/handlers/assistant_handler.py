"""Handler dédié aux intentions d'assistance générale, tâches, domotique et dialogue conversationnel."""
import logging
from typing import Any, Dict, Tuple

from app.core.models import IntentType, ParsedIntent
from app.core.llm.nlu_service import get_nlu_service

logger = logging.getLogger(__name__)


async def handle_assistant_intent(
    parsed: ParsedIntent,
    raw_query: str,
    session_ctx: Dict[str, Any],
    data: Dict[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    """Gère les intentions transversales (organisationnelles, domotique, budget et dialogue)."""
    import sys
    main_mod = sys.modules.get("app.main")
    nlu_service = main_mod.get_nlu_service() if (main_mod and hasattr(main_mod, "get_nlu_service")) else get_nlu_service()

    match parsed.intent:
        case IntentType.GET_BUDGET_BALANCE:
            cat = parsed.parameters.get("category", "général")
            spoken = f"Il vous reste actuellement 145 euros sur votre budget {cat} pour ce mois."

        case IntentType.LOG_EXPENSE:
            amount = parsed.parameters.get("amount", 0)
            cat = parsed.parameters.get("category", "divers")
            spoken = f"C'est enregistré : {amount} euros ajoutés aux dépenses {cat}."

        case IntentType.ADD_TASK:
            task = parsed.parameters.get("task", "tâche")
            spoken = f"Tâche enregistrée dans Google Tasks : {task}."

        case IntentType.LIST_TASKS:
            spoken = "Vous avez 2 tâches aujourd'hui : Rappeler le garage et arroser les plantes."

        case IntentType.SUMMARIZE_EMAILS:
            spoken = "Vous avez 1 e-mail important de votre banque concernant un relevé mensuel."

        case IntentType.TOGGLE_DEVICE:
            device = parsed.parameters.get("device", "appareil")
            action = "allumée" if parsed.parameters.get("action") == "on" else "éteinte"
            spoken = f"La {device} a bien été {action}."

        case IntentType.SMALL_TALK:
            sub_type = parsed.parameters.get("type", "ack")
            if sub_type == "thanks":
                spoken = "Avec plaisir ! N'hésitez pas si vous avez besoin d'autre chose."
            elif sub_type == "greeting":
                spoken = "Bonjour ! Que puis-je faire pour vous aujourd'hui ?"
            elif sub_type == "farewell":
                spoken = "Au revoir et bonne journée ! 👋"
            else:
                spoken = "Parfait ! Que souhaitez-vous faire d'autre ?"

        case IntentType.CONFIRM:
            # Si aucun pending_action formel mais qu'un historique de conversation existe
            if session_ctx.get("history") and nlu_service:
                llm_parsed = await nlu_service.parse(raw_query, context=session_ctx)
                if llm_parsed.conversational_reply:
                    spoken = llm_parsed.conversational_reply
                else:
                    spoken = "Parfait, c'est noté !"
            else:
                spoken = "C'est noté !"

        case IntentType.CANCEL:
            spoken = "Très bien, j'ai annulé l'opération."

        case _:
            reply = (
                parsed.conversational_reply
                or parsed.parameters.get("conversational_reply")
            )
            if reply:
                spoken = reply
            else:
                spoken = (
                    "Je n'ai pas bien compris votre demande. Vous pouvez me demander "
                    "de consulter ou planifier vos repas, gérer votre liste de courses, vos tâches ou votre budget. "
                    "Que souhaitez-vous faire ?"
                )

    return spoken, data
