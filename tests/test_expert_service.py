"""Boucle de l'expert Claude (niveau 2 de la cascade) avec un LLM scripté, hors ligne, et une base SQLite temporaire."""
from datetime import date
from typing import Any, Dict, List

import pytest

from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.agent_service import ConversationTurn
from app.core.agent.tools.sport_registry import build_sport_registry
from app.core.agent.tools.sport_tools import SportTools
from app.core.expert.errors import ExpertLoopLimitError, ExpertRefusalError, ExpertResponseError
from app.core.expert.expert_service import ExpertService
from app.core.expert.llm import ExpertTurn, ExpertUsage

TODAY = date(2026, 10, 19)
BASE_PROMPT = "Tu es Otis. Règles du domaine."


def text_turn(text: str, stop_reason: str = "end_turn") -> ExpertTurn:
    return ExpertTurn(
        content=[{"type": "text", "text": text}], stop_reason=stop_reason, model="claude-sonnet-5-5",
        usage=ExpertUsage(input_tokens=100, output_tokens=20),
    )


def tool_turn(*uses: Dict[str, Any]) -> ExpertTurn:
    content: List[Dict[str, Any]] = [{"type": "thinking", "thinking": "", "signature": "sig"}]
    content += [{"type": "tool_use", **use} for use in uses]
    return ExpertTurn(
        content=content, stop_reason="tool_use", model="claude-sonnet-5-5",
        usage=ExpertUsage(input_tokens=200, output_tokens=30),
    )


class ScriptedExpertLLM:
    def __init__(self, turns: List[Any]) -> None:
        self._turns = list(turns)
        self.requests: List[Dict[str, Any]] = []

    async def generate(self, *, system: str, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], max_tokens: int) -> ExpertTurn:
        self.requests.append({"system": system, "messages": [dict(m) for m in messages], "tools": tools, "max_tokens": max_tokens})
        if not self._turns:
            raise AssertionError("ScriptedExpertLLM : plus aucun tour scripté.")
        turn = self._turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn


@pytest.fixture
def db(isolate_sqlite_database):
    return isolate_sqlite_database


def _service(db, llm, max_llm_calls: int = 4) -> ExpertService:
    tools = SportTools(SqlSportConnector(db_manager=db), today=lambda: TODAY)
    return ExpertService(llm=llm, registry=build_sport_registry(tools), max_llm_calls=max_llm_calls)


@pytest.mark.asyncio
async def test_text_answer_with_history_and_short_answer_rules(db):
    llm = ScriptedExpertLLM([text_turn("Note la référence sur la plaque du frigo, puis commande la porte.")])
    history = [ConversationTurn(role="user", text="Salut"), ConversationTurn(role="assistant", text="Bonjour !")]

    reply = await _service(db, llm).run("Comment changer la porte de mon frigo ?", history, base_system=BASE_PROMPT)

    assert reply.text.startswith("Note la référence")
    assert reply.executions == []
    assert [u.output_tokens for u in reply.usages] == [20]
    request = llm.requests[0]
    assert request["system"].startswith(BASE_PROMPT)
    assert "courte" in request["system"]
    assert request["messages"] == [
        {"role": "user", "content": "Salut"},
        {"role": "assistant", "content": "Bonjour !"},
        {"role": "user", "content": "Comment changer la porte de mon frigo ?"},
    ]
    assert {t["name"] for t in request["tools"]} >= {"find_sport_sessions", "update_sport_session"}
    assert all(t["input_schema"]["type"] == "object" for t in request["tools"])


@pytest.mark.asyncio
async def test_detailed_mode_allows_a_longer_answer(db):
    short_llm = ScriptedExpertLLM([text_turn("Court.")])
    long_llm = ScriptedExpertLLM([text_turn("Long.")])

    await _service(db, short_llm).run("Q", base_system=BASE_PROMPT)
    await _service(db, long_llm).run("Q", base_system=BASE_PROMPT, detailed=True)

    assert long_llm.requests[0]["max_tokens"] > short_llm.requests[0]["max_tokens"]
    assert long_llm.requests[0]["system"] != short_llm.requests[0]["system"]


@pytest.mark.asyncio
async def test_tool_use_is_executed_and_results_sent_back_with_ids(db):
    session_id = db.add_sport_session({"date": "2026-10-18", "type_seance": "EF", "statut": "Réalisé"})
    first = tool_turn(
        {"id": "tu1", "name": "update_sport_session", "input": {"session_id": session_id, "changes": {"ressenti_rpe": 4}}},
        {"id": "tu2", "name": "update_sport_session", "input": {"session_id": 999, "changes": {"ressenti_rpe": 4}}},
    )
    llm = ScriptedExpertLLM([first, text_turn("C'est noté pour le footing d'hier.")])

    reply = await _service(db, llm).run("Mets 4 de RPE à hier", base_system=BASE_PROMPT)

    assert db.get_sport_session_by_id(session_id)["ressenti_rpe"] == 4
    assert [e.name for e in reply.executions] == ["update_sport_session", "update_sport_session"]
    assert len(reply.mutations) == 1
    assert len(reply.usages) == 2
    second = llm.requests[1]["messages"]
    assert second[-2] == {"role": "assistant", "content": first.content}
    results = second[-1]["content"]
    assert second[-1]["role"] == "user"
    assert [r["tool_use_id"] for r in results] == ["tu1", "tu2"]
    assert all(r["type"] == "tool_result" for r in results)
    assert "is_error" not in results[0] and results[1]["is_error"] is True
    assert "999" in results[1]["content"]


@pytest.mark.asyncio
async def test_refusal_raises_explicit_error(db):
    llm = ScriptedExpertLLM([text_turn("", stop_reason="refusal")])
    with pytest.raises(ExpertRefusalError):
        await _service(db, llm).run("Q", base_system=BASE_PROMPT)


@pytest.mark.asyncio
async def test_empty_answer_raises_explicit_error(db):
    llm = ScriptedExpertLLM([text_turn("   ")])
    with pytest.raises(ExpertResponseError, match="vide"):
        await _service(db, llm).run("Q", base_system=BASE_PROMPT)


@pytest.mark.asyncio
async def test_loop_limit_keeps_performed_executions_and_usages(db):
    use = {"id": "tu", "name": "find_sport_sessions", "input": {"limit": 1}}
    llm = ScriptedExpertLLM([tool_turn(use), tool_turn(use)])
    with pytest.raises(ExpertLoopLimitError) as info:
        await _service(db, llm, max_llm_calls=2).run("Q", base_system=BASE_PROMPT)
    assert len(info.value.executions) == 2
    assert len(info.value.usages) == 2
