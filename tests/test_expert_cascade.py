"""Cascade niveau 1 (agent Gemini) → niveau 2 (expert Claude), avec des LLM scriptés et une base SQLite temporaire."""
from datetime import date

import pytest

from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.agent_service import AgentService, ConversationTurn
from app.core.agent.errors import AgentResponseError, AgentUnavailableError
from app.core.agent.tool_registry import ToolRegistry
from app.core.agent.tools.escalation_tools import ESCALATION_TOOL_NAME, escalation_tool_definitions
from app.core.agent.tools.sport_registry import sport_tool_definitions
from app.core.agent.tools.sport_tools import SportTools
from app.core.expert.cascade import CascadeService
from app.core.expert.errors import ExpertUnavailableError
from app.core.expert.expert_service import ExpertService
from tests.agent_fakes import ScriptedLLM, call_turn, text_turn
from tests.test_expert_service import ScriptedExpertLLM, text_turn as expert_text

TODAY = date(2026, 10, 19)


@pytest.fixture
def db(isolate_sqlite_database):
    return isolate_sqlite_database


def _cascade(db, gemini, claude=None) -> CascadeService:
    tools = SportTools(SqlSportConnector(db_manager=db), today=lambda: TODAY)
    domain = sport_tool_definitions(tools)
    agent_tools = domain + (escalation_tool_definitions() if claude else [])
    agent = AgentService(llm=gemini, registry=ToolRegistry(agent_tools), sport_tools=tools, max_llm_calls=3)
    expert = ExpertService(llm=claude, registry=ToolRegistry(domain)) if claude else None
    return CascadeService(agent=agent, expert=expert)


def _escalate(question: str = "Comment changer la porte d'un frigo ?"):
    return call_turn({"name": ESCALATION_TOOL_NAME, "args": {"question": question}})


@pytest.mark.asyncio
async def test_simple_request_stays_on_gemini_and_the_expert_is_offered(db):
    gemini = ScriptedLLM([text_turn("Tu n'as rien de prévu.")])
    claude = ScriptedExpertLLM([])

    reply = await _cascade(db, gemini, claude).run("Qu'est-ce que j'ai aujourd'hui ?")

    assert (reply.text, reply.level) == ("Tu n'as rien de prévu.", "agent")
    assert reply.expert_usages == []
    assert ESCALATION_TOOL_NAME in {t["name"] for t in gemini.requests[0]["tools"]}


@pytest.mark.asyncio
async def test_escalation_hands_the_question_and_history_to_the_expert_without_a_second_gemini_call(db):
    gemini = ScriptedLLM([_escalate()])
    claude = ScriptedExpertLLM([expert_text("Relève la référence sur la plaque, puis commande la porte.")])
    history = [ConversationTurn(role="user", text="Salut"), ConversationTurn(role="assistant", text="Bonjour !")]

    reply = await _cascade(db, gemini, claude).run("Je dois changer la porte de mon frigo", history)

    assert reply.level == "expert"
    assert reply.escalation_reason == "demande"
    assert reply.text.startswith("Relève la référence")
    assert len(gemini.requests) == 1
    assert len(reply.expert_usages) == 1 and reply.expert_model == "claude-sonnet-5-5"
    request = claude.requests[0]
    assert request["messages"][-1]["content"] == "Je dois changer la porte de mon frigo"
    assert request["messages"][0] == {"role": "user", "content": "Salut"}
    assert "Comment changer la porte d'un frigo ?" in request["system"]  # reformulation de Gemini transmise
    assert ESCALATION_TOOL_NAME not in {t["name"] for t in request["tools"]}
    assert "Tu es Otis" in request["system"]  # consigne de l'agent réutilisée (date, règles métier)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [
    AgentResponseError("Réponse vide de Gemini (finishReason=STOP)."),
    AgentUnavailableError("Aucun modèle Gemini disponible."),
])
async def test_gemini_failure_without_change_is_handed_to_the_expert(db, failure):
    claude = ScriptedExpertLLM([expert_text("Voici la réponse.")])

    reply = await _cascade(db, ScriptedLLM([failure]), claude).run("Une question difficile")

    assert (reply.level, reply.text) == ("expert", "Voici la réponse.")
    assert reply.escalation_reason == f"echec_gemini:{type(failure).__name__}"
    assert len(reply.llm_calls) == 1  # l'appel Gemini raté reste journalisé


@pytest.mark.asyncio
async def test_gemini_failure_after_a_change_is_not_handed_over(db):
    session_id = db.add_sport_session({"date": "2026-10-19", "type_seance": "EF", "statut": "Réalisé"})
    gemini = ScriptedLLM([
        call_turn({"name": "update_sport_session", "args": {"session_id": session_id, "changes": {"ressenti_rpe": 4}}}),
        AgentResponseError("Réponse vide de Gemini."),
    ])
    claude = ScriptedExpertLLM([])
    cascade = _cascade(db, gemini, claude)
    cascade.agent.fast_replies = False

    with pytest.raises(AgentResponseError) as info:
        await cascade.run("Mets 4 de RPE et dis-moi un truc")
    assert len(info.value.executions) == 1
    assert claude.requests == []


@pytest.mark.asyncio
async def test_without_expert_gemini_failures_are_raised_as_before(db):
    with pytest.raises(AgentResponseError):
        await _cascade(db, ScriptedLLM([AgentResponseError("vide")])).run("Q")


@pytest.mark.asyncio
async def test_expert_follow_up_and_detailed_go_straight_to_the_expert(db):
    gemini = ScriptedLLM([])
    claude = ScriptedExpertLLM([expert_text("Merci, alors c'est la charnière."), expert_text("1. Dévisse…")])
    cascade = _cascade(db, gemini, claude)

    follow = await cascade.run("C'est un Bosch", expert_follow_up=True)
    detailed = await cascade.run("Approfondis", detailed=True)

    assert (follow.level, follow.escalation_reason) == ("expert", "suite")
    assert (detailed.level, detailed.escalation_reason) == ("expert", "approfondir")
    assert gemini.requests == []
    assert claude.requests[1]["max_tokens"] > claude.requests[0]["max_tokens"]


@pytest.mark.asyncio
async def test_expert_failure_after_escalation_keeps_the_gemini_calls(db):
    gemini = ScriptedLLM([_escalate()])
    claude = ScriptedExpertLLM([ExpertUnavailableError("Crédit Anthropic épuisé.")])

    with pytest.raises(ExpertUnavailableError) as info:
        await _cascade(db, gemini, claude).run("Une question difficile")
    assert len(info.value.llm_calls) == 1
    assert [e.name for e in info.value.executions] == [ESCALATION_TOOL_NAME]
