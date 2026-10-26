"""Handler de l'agent LLM à outils (Phase 6.8) : routage depuis /interact et mise en forme de la réponse."""
import logging
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.config import settings
from app.core.agent.errors import AgentError, AgentUnavailableError
from app.core.agent.factory import build_agent_service
from app.core.agent.agent_service import ConversationTurn
from app.core.agent.tool_registry import ToolExecution
from app.core.models import IntentType, ParsedIntent

logger = logging.getLogger(__name__)

# Intentions confiées à l'agent ; les autres (courses, repas, notes listées, apprentissage…) restent sur les regex.
AGENT_ROUTED_INTENTS = frozenset({
    IntentType.UNKNOWN,
    IntentType.GET_SPORT_SESSION,
    IntentType.LOG_SPORT_SESSION,
    IntentType.PLAN_SPORT_SESSION,
    IntentType.UPDATE_SPORT_SESSION,
    IntentType.PLAN_WEEKLY_TRAINING,
    IntentType.SAVE_NOTE,
})
# Garde-fou de la voie rapide « ajoute X » : une phrase de sport n'est jamais un article de courses.
_SPORT_WORDS = re.compile(
    r"\b(?:séances?|seances?|entra[iî]nements?|footing|fractionn[ée]|renfo|renforcement|sortie\s+longue|course\s+à\s+pied)\b",
    re.IGNORECASE,
)


class AgentTurnOutcome(BaseModel):
    parsed: ParsedIntent
    spoken: str
    data: Dict[str, Any]
    llm_model: Optional[str] = None


def routes_to_agent(parsed: ParsedIntent, query: str) -> bool:
    if settings.nlu_mode != "agent":
        return False
    if parsed.intent == IntentType.ADD_SHOPPING_ITEM:
        return bool(_SPORT_WORDS.search(query))
    return parsed.intent in AGENT_ROUTED_INTENTS


async def handle_agent_turn(query: str, session_ctx: Dict[str, Any], sport_connector: Any) -> AgentTurnOutcome:
    history = [
        ConversationTurn(role=h["role"], text=h["text"])
        for h in session_ctx.get("history", [])
        if h.get("role") in ("user", "assistant") and h.get("text")
    ]
    service = None
    try:
        service = build_agent_service(sport_connector)
        reply = await service.run(query, history)
    except AgentError as exc:
        logger.error(f"Agent en échec ({type(exc).__name__}) : {exc}")
        data = _response_data(exc.executions, session_ctx)
        data["error"] = str(exc)
        return AgentTurnOutcome(
            parsed=ParsedIntent(intent=IntentType.AGENT, confidence=0.0, parameters={"error": str(exc)}, raw_query=query),
            spoken=_failure_message(exc),
            data=data,
            llm_model=getattr(service.llm, "last_model", None) if service else None,
        )

    return AgentTurnOutcome(
        parsed=ParsedIntent(
            intent=IntentType.AGENT,
            confidence=1.0,
            parameters={"tools": [e.name for e in reply.executions]},
            raw_query=query,
        ),
        spoken=reply.text,
        data=_response_data(reply.executions, session_ctx),
        llm_model=getattr(service.llm, "last_model", None),
    )


def _response_data(executions: List[ToolExecution], session_ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Expose la trace des outils et les clés attendues par la PWA (rafraîchissement sport, toast d'annulation)."""
    data: Dict[str, Any] = {
        "tool_calls": [{"name": e.name, "args": e.args, "error": e.error} for e in executions],
    }
    for execution in executions:
        if execution.error:
            continue
        if execution.undos:
            created = execution.response.get("created") or [None]
            data["session"] = execution.response.get("session") or created[-1]
        if "note_id" in execution.response:
            data.update(note_id=execution.response["note_id"], category=execution.response["category"])
            session_ctx["last_undoable_action"] = {
                "type": "save_note",
                "note_id": execution.response["note_id"],
                "content": execution.response["content"],
            }
    return data


def _failure_message(exc: AgentError) -> str:
    if isinstance(exc, AgentUnavailableError):
        message = "Mon cerveau Gemini est indisponible pour le moment."
    else:
        message = "Je n'ai pas réussi à traiter ta demande jusqu'au bout."
    mutations = [e for e in exc.executions if e.undos]
    if not mutations:
        return f"{message} Je n'ai rien modifié, réessaie dans un instant."
    count = sum(len(e.undos) for e in mutations)
    plural = "s" if count > 1 else ""
    return (
        f"{message} Attention : {count} modification{plural} du carnet a{'vaient' if plural else 'vait'} "
        f"déjà été appliquée{plural} avant l'erreur, vérifie ta séance."
    )
