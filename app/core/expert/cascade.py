"""Cerveau en cascade (Phase 6.10) : agent Gemini (niveau 1) puis, si besoin, expert Claude (niveau 2).

Passage à l'expert :
- « demande » : Gemini appelle l'outil demander_expert ;
- « echec_gemini:<Erreur> » : Gemini échoue (réponse vide, mal formée, indisponible…) sans avoir rien modifié ;
- « suite » : le tour précédent de l'expert posait une question, la réponse lui revient directement ;
- « approfondir » : l'utilisateur demande une réponse détaillée.
Un échec de Gemini après une modification n'est jamais confié à l'expert : il est signalé tel quel (mutations listées).
"""
from typing import List, Literal, Optional, Sequence

from pydantic import BaseModel

from app.core.agent.agent_service import AgentService, ConversationTurn, LLMCall
from app.core.agent.errors import AgentError
from app.core.agent.tool_registry import ToolExecution
from app.core.agent.undo import AgentUndo
from app.core.expert.errors import ExpertError
from app.core.expert.expert_service import ExpertService
from app.core.expert.llm import ExpertUsage


class CascadeReply(BaseModel):
    text: str
    executions: List[ToolExecution]
    llm_calls: List[LLMCall] = []
    fast_reply: bool = False
    level: Literal["agent", "expert"] = "agent"
    escalation_reason: Optional[str] = None
    expert_usages: List[ExpertUsage] = []
    expert_model: Optional[str] = None

    @property
    def mutations(self) -> List[AgentUndo]:
        return [undo for e in self.executions for undo in e.undos]


class CascadeService:
    def __init__(
        self, agent: AgentService, expert: Optional[ExpertService], expert_disabled: Optional[str] = None,
    ) -> None:
        """`expert` absent (clé Anthropic non configurée, budget atteint) : l'agent Gemini répond seul, comme avant la
        Phase 6.10. `expert_disabled` : raison explicite quand l'expert est configuré mais coupé (ex. budget)."""
        self.agent = agent
        self.expert = expert
        self.expert_disabled = expert_disabled

    @property
    def llm(self):
        """Compatibilité avec l'appelant (modèle Gemini du dernier appel)."""
        return self.agent.llm

    async def run(
        self, query: str, history: Sequence[ConversationTurn] = (), ui_context: Optional[str] = None,
        ui_session_id: Optional[int] = None, expert_follow_up: bool = False, detailed: bool = False,
    ) -> CascadeReply:
        if self.expert and (expert_follow_up or detailed):
            reason = "approfondir" if detailed else "suite"
            return await self._expert(query, history, ui_context, ui_session_id, reason, detailed=detailed)

        try:
            reply = await self.agent.run(query, history, ui_context=ui_context, ui_session_id=ui_session_id)
        except AgentError as exc:
            if self.expert is None or any(e.undos for e in exc.executions):
                raise
            return await self._expert(
                query, history, ui_context, ui_session_id, f"echec_gemini:{type(exc).__name__}",
                executions=exc.executions, llm_calls=exc.llm_calls,
            )

        if reply.escalation is None:
            return CascadeReply(
                text=reply.text, executions=reply.executions, llm_calls=reply.llm_calls, fast_reply=reply.fast_reply,
            )
        return await self._expert(
            query, history, ui_context, ui_session_id, "demande", handover=reply.escalation,
            executions=reply.executions, llm_calls=reply.llm_calls,
        )

    async def _expert(
        self, query: str, history: Sequence[ConversationTurn], ui_context: Optional[str],
        ui_session_id: Optional[int], reason: str, *, detailed: bool = False, handover: Optional[str] = None,
        executions: Sequence[ToolExecution] = (), llm_calls: Sequence[LLMCall] = (),
    ) -> CascadeReply:
        if self.expert is None:
            raise RuntimeError("Passage à l'expert demandé alors qu'aucun expert Claude n'est configuré.")
        base_system = self.agent.system_prompt(query, history, ui_context, ui_session_id)
        try:
            reply = await self.expert.run(
                query, history, base_system=base_system, detailed=detailed, handover=handover,
            )
        except ExpertError as exc:
            exc.executions = [*executions, *exc.executions]
            exc.llm_calls = list(llm_calls)
            raise
        return CascadeReply(
            text=reply.text,
            executions=[*executions, *reply.executions],
            llm_calls=list(llm_calls),
            level="expert",
            escalation_reason=reason,
            expert_usages=reply.usages,
            expert_model=reply.model,
        )
