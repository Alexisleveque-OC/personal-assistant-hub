"""Boucle agent : Gemini raisonne, appelle les outils métier (function calling), puis formule la réponse vocale."""
from typing import Any, Dict, List, Literal, Sequence

from pydantic import BaseModel

from app.core.agent.errors import AgentError, AgentLoopLimitError, AgentResponseError
from app.core.agent.llm import AgentLLM
from app.core.agent.prompt import build_system_prompt
from app.core.agent.tool_registry import ToolExecution, ToolRegistry
from app.core.agent.tools.sport_models import FindSessionsArgs, UndoSnapshot
from app.core.agent.tools.sport_tools import SportTools

__all__ = ["AgentLoopLimitError", "AgentReply", "AgentResponseError", "AgentService", "ConversationTurn"]

RECENT_SESSIONS_LIMIT = 12
_FAILED_FINISH_REASONS = {"MALFORMED_FUNCTION_CALL", "UNEXPECTED_TOOL_CALL", "TOO_MANY_TOOL_CALLS"}


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class AgentReply(BaseModel):
    text: str
    executions: List[ToolExecution]

    @property
    def mutations(self) -> List[UndoSnapshot]:
        return [e.undo for e in self.executions if e.undo is not None]


class AgentService:
    def __init__(self, llm: AgentLLM, registry: ToolRegistry, sport_tools: SportTools, max_llm_calls: int = 4) -> None:
        self.llm = llm
        self.registry = registry
        self.sport_tools = sport_tools
        self.max_llm_calls = max_llm_calls

    async def run(self, query: str, history: Sequence[ConversationTurn] = ()) -> AgentReply:
        recent = self.sport_tools.find_sport_sessions(FindSessionsArgs(limit=RECENT_SESSIONS_LIMIT))
        system_instruction = build_system_prompt(self.sport_tools.today(), recent)
        contents: List[Dict[str, Any]] = [
            {"role": "model" if turn.role == "assistant" else "user", "parts": [{"text": turn.text}]} for turn in history
        ]
        contents.append({"role": "user", "parts": [{"text": query}]})
        declarations = self.registry.declarations()
        executions: List[ToolExecution] = []

        try:
            for _ in range(self.max_llm_calls):
                turn = await self.llm.generate(system_instruction=system_instruction, contents=contents, tools=declarations)
                if turn.finish_reason in _FAILED_FINISH_REASONS:
                    raise AgentResponseError(f"Gemini a interrompu sa réponse ({turn.finish_reason}).")

                calls = turn.function_calls()
                if not calls:
                    text = turn.text()
                    if not text:
                        raise AgentResponseError(f"Réponse vide de Gemini (finishReason={turn.finish_reason}).")
                    return AgentReply(text=text, executions=executions)

                contents.append({"role": "model", "parts": turn.parts})
                response_parts = []
                for call in calls:
                    execution = self.registry.execute(call.name, call.args)
                    executions.append(execution)
                    function_response: Dict[str, Any] = {"name": call.name, "response": execution.response}
                    if call.id:
                        function_response["id"] = call.id
                    response_parts.append({"functionResponse": function_response})
                contents.append({"role": "user", "parts": response_parts})

            raise AgentLoopLimitError(f"Limite de {self.max_llm_calls} appels Gemini atteinte sans réponse finale.")
        except AgentError as exc:
            exc.executions = executions
            raise
