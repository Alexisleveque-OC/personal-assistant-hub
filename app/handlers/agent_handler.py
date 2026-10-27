"""Handler de l'agent LLM à outils (Phase 6.8) : routage depuis /interact et mise en forme de la réponse."""
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.config import settings
from app.core.agent.errors import AgentError, AgentUnavailableError
from app.core.agent.factory import build_agent_service, build_undo_service
from app.core.agent.agent_service import ConversationTurn
from app.core.agent.tool_registry import ToolExecution
from app.core.agent.tools.meals_tools import MealsTools
from app.core.agent.undo import UndoError, UndoJournal
from app.core.database import get_database_manager
from app.core.models import IntentType, ParsedIntent
from app.core.shopping.rayon_questions import RAYON_QUESTION_KEY
from app.handlers.fast_lane import FAST_LANE_INTENTS, is_fast_lane
from app.handlers.rayon_question_handler import ask_rayon_question

logger = logging.getLogger(__name__)

# Intentions confiées à l'agent. Les intentions de la voie rapide (`FAST_LANE_INTENTS`) n'y vont que si la phrase
# est ambiguë ; les autres (notes listées, apprentissage, confirmations en attente…) restent sur les regex.
AGENT_ROUTED_INTENTS = frozenset({
    IntentType.UNKNOWN,
    IntentType.GET_SPORT_SESSION,
    IntentType.LOG_SPORT_SESSION,
    IntentType.PLAN_SPORT_SESSION,
    IntentType.UPDATE_SPORT_SESSION,
    IntentType.PLAN_WEEKLY_TRAINING,
    IntentType.SAVE_NOTE,
    IntentType.SET_MEAL_PLAN,
    IntentType.GET_RECIPE_INGREDIENTS,
    IntentType.ADD_RECIPE_INGREDIENTS,
    IntentType.MARK_SHOPPING_BOUGHT,
    IntentType.CHECK_SHOPPING_COMPLETION,
})


class AgentTurnOutcome(BaseModel):
    parsed: ParsedIntent
    spoken: str
    data: Dict[str, Any]
    llm_model: Optional[str] = None


def routes_to_agent(parsed: ParsedIntent, query: str, awaiting_agent_reply: bool = False) -> bool:
    """`awaiting_agent_reply` : le tour précédent de l'agent posait une question (« d'accord » y répond)."""
    if settings.nlu_mode != "agent":
        return False
    if parsed.intent in FAST_LANE_INTENTS:
        return not is_fast_lane(parsed, query)
    if awaiting_agent_reply and parsed.intent == IntentType.SMALL_TALK:
        return True
    return parsed.intent in AGENT_ROUTED_INTENTS


def routes_to_agent_undo(parsed: ParsedIntent, session_ctx: Dict[str, Any]) -> bool:
    """« Annule ça » vise le journal de l'agent, sauf si la dernière action vient du flux regex (courses…)."""
    return (
        settings.nlu_mode == "agent"
        and parsed.intent == IntentType.UNDO_LAST_ACTION
        and "last_undoable_action" not in session_ctx
    )


def handle_agent_undo(query: str, session_id: str, sport_connector: Any, meals_connector: Any = None) -> AgentTurnOutcome:
    """Annulation déterministe (sans LLM) du dernier tour d'actions de l'agent."""
    try:
        outcome = build_undo_service(sport_connector, meals_connector).undo_last(session_id)
    except (UndoError, AgentUnavailableError) as exc:
        return AgentTurnOutcome(
            parsed=ParsedIntent(
                intent=IntentType.UNDO_LAST_ACTION, confidence=1.0, parameters={"error": str(exc)}, raw_query=query,
            ),
            spoken=str(exc),
            data={"error": str(exc)},
        )
    data: Dict[str, Any] = {"undone_action": outcome.model_dump()}
    if outcome.sport_session_ids:
        data["session"] = {"id": outcome.sport_session_ids[0]}  # déclenche le rafraîchissement des vues sport
    return AgentTurnOutcome(
        parsed=ParsedIntent(
            intent=IntentType.UNDO_LAST_ACTION, confidence=1.0, parameters={"batch_id": outcome.batch_id}, raw_query=query,
        ),
        spoken=f"C'est annulé : {', '.join(outcome.restored)}.",
        data=data,
    )


async def handle_agent_turn(
    query: str, session_id: str, session_ctx: Dict[str, Any], sport_connector: Any, meals_connector: Any = None,
) -> AgentTurnOutcome:
    history = [
        ConversationTurn(role=h["role"], text=h["text"])
        for h in session_ctx.get("history", [])
        if h.get("role") in ("user", "assistant") and h.get("text")
    ]
    # Une clarification regex en attente (ex. choix de rayon) est obsolète dès que l'agent reprend la main.
    session_ctx.pop("pending_action", None)
    meals_tools = MealsTools(
        meals_connector, confirmable_dishes=session_ctx.pop("meal_confirmation_pending", []), user_words=query,
    )
    service = None
    try:
        service = build_agent_service(
            sport_connector, session_id, "last_undoable_action" in session_ctx, meals_tools, history,
        )
        reply = await service.run(query, history)
    except AgentError as exc:
        logger.error(f"Agent en échec ({type(exc).__name__}) : {exc}")
        _journalize(session_id, session_ctx, exc.executions)
        data = _response_data(exc.executions)
        data["error"] = str(exc)
        _add_latency_details(data, exc.llm_calls, fast_reply=False)
        return AgentTurnOutcome(
            parsed=ParsedIntent(intent=IntentType.AGENT, confidence=0.0, parameters={"error": str(exc)}, raw_query=query),
            spoken=_failure_message(exc),
            data=data,
            llm_model=getattr(service.llm, "last_model", None) if service else None,
        )

    _journalize(session_id, session_ctx, reply.executions)
    if "?" in reply.text:
        session_ctx["agent_awaiting_reply"] = True
    if meals_tools.refused_dishes:
        session_ctx["meal_confirmation_pending"] = meals_tools.refused_dishes
    spoken, data = reply.text, _response_data(reply.executions)
    _add_latency_details(data, reply.llm_calls, reply.fast_reply)
    if meals_tools.unknown_articles:
        # Article au rayon inconnu : la question est posée par l'application, la réponse traitée sans LLM.
        question = await ask_rayon_question(meals_tools.unknown_articles, session_ctx, meals_connector)
        spoken, data["rayon_question"] = f"{spoken} {question}", session_ctx[RAYON_QUESTION_KEY]
    return AgentTurnOutcome(
        parsed=ParsedIntent(
            intent=IntentType.AGENT,
            confidence=1.0,
            parameters={"tools": [e.name for e in reply.executions]},
            raw_query=query,
        ),
        spoken=spoken,
        data=data,
        llm_model=getattr(service.llm, "last_model", None),
    )


def _journalize(session_id: str, session_ctx: Dict[str, Any], executions: List[ToolExecution]) -> None:
    """Persiste les instantanés du tour : l'action de l'agent devient la dernière action annulable."""
    undos = [undo for e in executions for undo in e.undos]
    if UndoJournal(get_database_manager()).record(session_id, undos) is not None:
        session_ctx.pop("last_undoable_action", None)


def _add_latency_details(data: Dict[str, Any], llm_calls: List[Any], fast_reply: bool) -> None:
    """Détail journalisé dans conversation_logs.parameters : durée de chaque appel Gemini, réponse directe ou non."""
    data["llm_calls"] = [call.model_dump() for call in llm_calls]
    data["fast_reply"] = fast_reply


def _response_data(executions: List[ToolExecution]) -> Dict[str, Any]:
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
        if execution.response.get("ajoutes"):
            data.setdefault("items", []).extend(execution.response["ajoutes"])  # toast « article(s) ajouté(s) »
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
        f"{message} Attention : {count} modification{plural} a{'vaient' if plural else 'vait'} "
        f"déjà été appliquée{plural} avant l'erreur. Dis « annule ça » pour revenir en arrière."
    )
