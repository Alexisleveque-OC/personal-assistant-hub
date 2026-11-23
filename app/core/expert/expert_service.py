"""Boucle de l'expert Claude : raisonne, appelle si besoin les outils d'Otis (même registre que l'agent Gemini),
puis formule une réponse courte adaptée à l'oral (ou détaillée sur demande « Approfondir »)."""
import json
import logging
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel

from app.core.agent.agent_service import ConversationTurn
from app.core.agent.tool_registry import ToolExecution, ToolRegistry
from app.core.agent.undo import AgentUndo
from app.core.expert.errors import ExpertError, ExpertLoopLimitError, ExpertRefusalError, ExpertResponseError
from app.core.expert.llm import ExpertLLM, ExpertUsage

logger = logging.getLogger(__name__)

SHORT_MAX_TOKENS = 2000  # réflexion (effort bas) + 2 à 4 phrases
DETAILED_MAX_TOKENS = 6000

_EXPERT_RULES = """\

Tu es maintenant l'expert d'Otis : l'agent habituel t'a confié cette demande parce qu'elle demande du raisonnement,
des conseils ou sort de ses outils. Tu restes Otis pour l'utilisateur."""

_SHORT_RULES = """\
Ta réponse est lue à voix haute : 2 à 4 phrases courtes, sans listes, titres, markdown ni émojis. Va à l'essentiel ;
si le sujet mérite plus de détails, l'utilisateur pourra demander d'approfondir."""

_DETAILED_RULES = """\
L'utilisateur a demandé d'approfondir : ta réponse s'affiche à l'écran. Donne les étapes concrètes, courtes et
numérotées, sans titres markdown, en 15 lignes au plus."""

_COMMON_RULES = """\
Si la demande est ambiguë ou qu'il te manque une information indispensable, ne devine pas : pose une seule question
courte pour faire préciser. Utilise les outils d'Otis (courses, repas, tâches, agenda, sport, notes) seulement si
l'utilisateur le demande ou si c'est clairement utile. N'affirme jamais avoir fait une action que tu n'as pas faite."""


class ExpertReply(BaseModel):
    text: str
    executions: List[ToolExecution]
    usages: List[ExpertUsage]
    model: Optional[str] = None

    @property
    def mutations(self) -> List[AgentUndo]:
        return [undo for e in self.executions for undo in e.undos]


def build_expert_system(base_system: str, detailed: bool, handover: Optional[str] = None) -> str:
    """`handover` : demande reformulée par l'agent Gemini au moment de passer la main."""
    length_rules = _DETAILED_RULES if detailed else _SHORT_RULES
    note = f"\nDemande transmise par l'agent : {handover}" if handover else ""
    return f"{base_system}\n{_EXPERT_RULES}{note}\n{length_rules}\n{_COMMON_RULES}"


class ExpertService:
    def __init__(self, llm: ExpertLLM, registry: ToolRegistry, max_llm_calls: int = 4) -> None:
        self.llm = llm
        self.registry = registry
        self.max_llm_calls = max_llm_calls

    async def run(
        self, query: str, history: Sequence[ConversationTurn] = (), *, base_system: str, detailed: bool = False,
        handover: Optional[str] = None,
    ) -> ExpertReply:
        """`base_system` : consigne de l'agent (date, règles métier, séances récentes) que l'expert complète."""
        system = build_expert_system(base_system, detailed, handover)
        max_tokens = DETAILED_MAX_TOKENS if detailed else SHORT_MAX_TOKENS
        messages: List[Dict[str, Any]] = [{"role": turn.role, "content": turn.text} for turn in history]
        messages.append({"role": "user", "content": query})
        tools = self.registry.claude_declarations()
        executions: List[ToolExecution] = []
        usages: List[ExpertUsage] = []

        try:
            for _ in range(self.max_llm_calls):
                turn = await self.llm.generate(system=system, messages=messages, tools=tools, max_tokens=max_tokens)
                usages.append(turn.usage if turn.usage.model else turn.usage.model_copy(update={"model": turn.model}))
                if turn.stop_reason == "refusal":
                    raise ExpertRefusalError("Claude a refusé de répondre à cette demande.")

                uses = turn.tool_uses()
                if not uses:
                    text = turn.text()
                    if not text:
                        raise ExpertResponseError(f"Réponse vide de Claude (stop_reason={turn.stop_reason}).")
                    if turn.stop_reason == "max_tokens":
                        logger.warning("Expert : réponse tronquée par max_tokens.")
                    return ExpertReply(text=text, executions=executions, usages=usages, model=turn.model)

                messages.append({"role": "assistant", "content": turn.content})
                results = []
                for use in uses:
                    execution = await self.registry.execute(use["name"], use.get("input") or {})
                    executions.append(execution)
                    result: Dict[str, Any] = {
                        "type": "tool_result",
                        "tool_use_id": use["id"],
                        "content": json.dumps(execution.response, ensure_ascii=False),
                    }
                    if execution.error:
                        result["is_error"] = True
                    results.append(result)
                messages.append({"role": "user", "content": results})

            raise ExpertLoopLimitError(f"Limite de {self.max_llm_calls} appels Claude atteinte sans réponse finale.")
        except ExpertError as exc:
            exc.executions = executions
            exc.usages = usages
            raise
