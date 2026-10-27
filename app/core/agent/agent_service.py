"""Boucle agent : Gemini raisonne, appelle les outils métier (function calling), puis formule la réponse vocale."""
import time
from typing import Any, Dict, List, Literal, Optional, Sequence

from pydantic import BaseModel

from app.core.agent.errors import AgentError, AgentLoopLimitError, AgentResponseError
from app.core.agent.fast_reply import fast_reply
from app.core.agent.llm import AgentLLM
from app.core.agent.prompt import build_system_prompt
from app.core.agent.tool_registry import ToolExecution, ToolRegistry
from app.core.agent.tools.session_types import cited_session_types
from app.core.agent.tools.sport_models import FindSessionsArgs
from app.core.agent.tools.sport_tools import SportTools
from app.core.agent.undo import AgentUndo

__all__ = ["AgentLoopLimitError", "AgentReply", "AgentResponseError", "AgentService", "ConversationTurn"]

RECENT_SESSIONS_LIMIT = 12
_FAILED_FINISH_REASONS = {"MALFORMED_FUNCTION_CALL", "UNEXPECTED_TOOL_CALL", "TOO_MANY_TOOL_CALLS"}


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class LLMCall(BaseModel):
    """Mesure d'un appel Gemini (relais de modèles compris), journalisée avec le tour."""
    model: Optional[str] = None
    ms: float


class AgentReply(BaseModel):
    text: str
    executions: List[ToolExecution]
    llm_calls: List[LLMCall] = []
    fast_reply: bool = False

    @property
    def mutations(self) -> List[AgentUndo]:
        return [undo for e in self.executions for undo in e.undos]


class AgentService:
    def __init__(
        self, llm: AgentLLM, registry: ToolRegistry, sport_tools: SportTools, max_llm_calls: int = 4,
        fast_replies: bool = True,
    ) -> None:
        """`fast_replies` : après une modification simple, l'application rédige la réponse (pas de 2e appel Gemini)."""
        self.llm = llm
        self.registry = registry
        self.sport_tools = sport_tools
        self.max_llm_calls = max_llm_calls
        self.fast_replies = fast_replies

    async def run(self, query: str, history: Sequence[ConversationTurn] = ()) -> AgentReply:
        previous_user_turns = [turn.text for turn in history if turn.role == "user"][-1:]
        self.sport_tools.cited_types = frozenset(cited_session_types([query, *previous_user_turns]))
        recent = self.sport_tools.find_sport_sessions(FindSessionsArgs(limit=RECENT_SESSIONS_LIMIT))
        system_instruction = build_system_prompt(self.sport_tools.today(), recent)
        contents: List[Dict[str, Any]] = [
            {"role": "model" if turn.role == "assistant" else "user", "parts": [{"text": turn.text}]} for turn in history
        ]
        contents.append({"role": "user", "parts": [{"text": query}]})
        declarations = self.registry.declarations()
        executions: List[ToolExecution] = []
        llm_calls: List[LLMCall] = []

        try:
            for _ in range(self.max_llm_calls):
                start = time.perf_counter()
                try:
                    turn = await self.llm.generate(
                        system_instruction=system_instruction, contents=contents, tools=declarations,
                    )
                finally:
                    llm_calls.append(LLMCall(
                        model=getattr(self.llm, "last_model", None), ms=round((time.perf_counter() - start) * 1000, 1),
                    ))
                if turn.finish_reason in _FAILED_FINISH_REASONS:
                    raise AgentResponseError(f"Gemini a interrompu sa réponse ({turn.finish_reason}).")

                calls = turn.function_calls()
                if not calls:
                    text = turn.text()
                    if not text:
                        raise AgentResponseError(f"Réponse vide de Gemini (finishReason={turn.finish_reason}).")
                    return AgentReply(text=text, executions=executions, llm_calls=llm_calls)

                contents.append({"role": "model", "parts": turn.parts})
                response_parts = []
                turn_executions: List[ToolExecution] = []
                for call in calls:
                    execution = await self.registry.execute(call.name, call.args)
                    turn_executions.append(execution)
                    function_response: Dict[str, Any] = {"name": call.name, "response": execution.response}
                    if call.id:
                        function_response["id"] = call.id
                    response_parts.append({"functionResponse": function_response})
                executions.extend(turn_executions)
                text = fast_reply(query, turn_executions) if self.fast_replies else None
                if text:
                    return AgentReply(text=text, executions=executions, llm_calls=llm_calls, fast_reply=True)
                contents.append({"role": "user", "parts": response_parts})

            raise AgentLoopLimitError(f"Limite de {self.max_llm_calls} appels Gemini atteinte sans réponse finale.")
        except AgentError as exc:
            exc.executions = executions
            exc.llm_calls = llm_calls
            raise
