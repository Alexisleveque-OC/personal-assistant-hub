"""Tests de la boucle agent (function calling) avec un LLM scripté et une base SQLite temporaire."""
from datetime import date

import pytest

from app.connectors.sheets.sport_models import SportSessionType
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.agent_service import AgentLoopLimitError, AgentResponseError, AgentService, ConversationTurn
from app.core.agent.llm import AgentUnavailableError, LLMTurn
from app.core.agent.tools.sport_registry import build_sport_registry
from app.core.agent.tools.sport_tools import SportTools
from tests.agent_fakes import ScriptedLLM, call_turn, text_turn

TODAY = date(2026, 10, 19)  # lundi


@pytest.fixture
def db(isolate_sqlite_database):
    return isolate_sqlite_database


def _service(db, llm, max_llm_calls: int = 4) -> AgentService:
    tools = SportTools(SqlSportConnector(db_manager=db), today=lambda: TODAY)
    return AgentService(llm=llm, registry=build_sport_registry(tools), sport_tools=tools, max_llm_calls=max_llm_calls)


def _seed(db, day: str, type_seance: str, **fields) -> int:
    return db.add_sport_session({"date": day, "type_seance": type_seance, "statut": "Réalisé", **fields})


@pytest.mark.asyncio
async def test_text_reply_with_date_recent_sessions_and_history_in_request(db):
    renfo = _seed(db, "2026-10-15", "Renforcement")
    llm = ScriptedLLM([text_turn("Bonjour !")])

    reply = await _service(db, llm).run(
        "Salut",
        history=[ConversationTurn(role="user", text="Coucou"), ConversationTurn(role="assistant", text="Salut toi")],
    )

    assert reply.text == "Bonjour !"
    assert reply.executions == []
    request = llm.requests[0]
    assert "lundi 19/10/2026" in request["system_instruction"]
    assert f"id={renfo}" in request["system_instruction"]
    assert [c["role"] for c in request["contents"]] == ["user", "model", "user"]
    assert request["contents"][-1]["parts"] == [{"text": "Salut"}]
    assert {d["name"] for d in request["tools"]} >= {"find_sport_sessions", "update_sport_session"}


@pytest.mark.asyncio
async def test_function_call_is_executed_and_model_turn_echoed_verbatim(db):
    renfo = _seed(db, "2026-10-15", "Renforcement")
    today_ef = _seed(db, "2026-10-19", "EF")
    model_turn = call_turn({"name": "update_sport_session", "args": {"session_id": renfo, "changes": {"ressenti_rpe": 3}}})
    llm = ScriptedLLM([model_turn, text_turn("C'est noté, RPE 3 pour le renfo du jeudi 15/10.")])

    reply = await _service(db, llm).run("Mets le RPE de mon dernier renfo à 3")

    assert db.get_sport_session_by_id(renfo)["ressenti_rpe"] == 3
    assert db.get_sport_session_by_id(today_ef)["ressenti_rpe"] is None
    assert reply.text.startswith("C'est noté")
    assert [e.name for e in reply.executions] == ["update_sport_session"]
    assert len(reply.mutations) == 1 and reply.mutations[0].session_id == renfo

    second_contents = llm.requests[1]["contents"]
    assert second_contents[-2] == {"role": "model", "parts": model_turn.parts}
    assert second_contents[-2]["parts"][0]["thoughtSignature"] == "sig-1"
    function_response = second_contents[-1]["parts"][0]["functionResponse"]
    assert second_contents[-1]["role"] == "user"
    assert function_response["name"] == "update_sport_session"
    assert function_response["response"]["session"]["ressenti_rpe"] == 3


@pytest.mark.asyncio
async def test_parallel_calls_answered_in_one_turn_in_order_with_ids(db):
    first = _seed(db, "2026-10-18", "EF")
    second = _seed(db, "2026-10-17", "EF")
    turn = call_turn(
        {"id": "c1", "name": "get_sport_session", "args": {"session_id": first}},
        {"id": "c2", "name": "get_sport_session", "args": {"session_id": second}},
    )
    llm = ScriptedLLM([turn, text_turn("Voilà.")])

    await _service(db, llm).run("Détaille mes deux dernières séances")

    parts = llm.requests[1]["contents"][-1]["parts"]
    assert [p["functionResponse"]["id"] for p in parts] == ["c1", "c2"]
    assert [p["functionResponse"]["response"]["session"]["id"] for p in parts] == [first, second]


@pytest.mark.asyncio
async def test_tool_errors_are_sent_back_and_loop_continues(db):
    llm = ScriptedLLM([
        call_turn({"name": "update_sport_session", "args": {"session_id": 77, "changes": {"ressenti_rpe": 4}}}),
        text_turn("Je ne trouve pas cette séance, laquelle veux-tu modifier ?"),
    ])
    reply = await _service(db, llm).run("Mets 4 de RPE")

    error_part = llm.requests[1]["contents"][-1]["parts"][0]["functionResponse"]
    assert "77" in error_part["response"]["error"]
    assert reply.executions[0].error is not None
    assert reply.mutations == []


@pytest.mark.asyncio
async def test_thought_parts_are_not_spoken(db):
    llm = ScriptedLLM([LLMTurn(parts=[{"text": "réflexion interne", "thought": True}, {"text": "Réponse."}], finish_reason="STOP")])
    reply = await _service(db, llm).run("Question")
    assert reply.text == "Réponse."


@pytest.mark.asyncio
async def test_loop_limit_raises_with_performed_executions(db):
    looping = call_turn({"name": "find_sport_sessions", "args": {}})
    llm = ScriptedLLM([looping, looping, looping])
    with pytest.raises(AgentLoopLimitError) as exc_info:
        await _service(db, llm, max_llm_calls=3).run("Boucle")
    assert len(llm.requests) == 3
    assert len(exc_info.value.executions) == 3


@pytest.mark.asyncio
async def test_llm_failure_after_mutation_reports_the_mutation(db):
    session_id = _seed(db, "2026-10-19", "EF")
    llm = ScriptedLLM([
        call_turn({"name": "update_sport_session", "args": {"session_id": session_id, "changes": {"ressenti_rpe": 6}}}),
        AgentUnavailableError("Gemini indisponible (503)"),
    ])
    with pytest.raises(AgentUnavailableError) as exc_info:
        await _service(db, llm).run("RPE 6")
    assert [u.session_id for e in exc_info.value.executions for u in e.undos] == [session_id]


@pytest.mark.asyncio
async def test_malformed_function_call_raises_explicit_error(db):
    llm = ScriptedLLM([LLMTurn(parts=[], finish_reason="MALFORMED_FUNCTION_CALL")])
    with pytest.raises(AgentResponseError, match="MALFORMED_FUNCTION_CALL"):
        await _service(db, llm).run("Quelque chose")


@pytest.mark.asyncio
async def test_empty_answer_raises_explicit_error(db):
    llm = ScriptedLLM([LLMTurn(parts=[{"text": "  "}], finish_reason="STOP")])
    with pytest.raises(AgentResponseError, match="vide"):
        await _service(db, llm).run("Quelque chose")


@pytest.mark.asyncio
async def test_types_cited_in_the_query_and_recent_user_turns_are_given_to_the_sport_tools(db):
    tools = SportTools(SqlSportConnector(db_manager=db), today=lambda: TODAY)
    service = AgentService(llm=ScriptedLLM([text_turn("Ok")]), registry=build_sport_registry(tools), sport_tools=tools)

    await service.run("il fallait mettre son RPE à 3", history=[
        ConversationTurn(role="user", text="Le footing de samedi"),
        ConversationTurn(role="assistant", text="Ton renfo ?"),
        ConversationTurn(role="user", text="Non, je parlais de ma séance de renforcement"),
        ConversationTurn(role="assistant", text="D'accord."),
    ])

    assert tools.cited_types == {SportSessionType.RENFORCEMENT}  # phrase courante + dernier tour utilisateur
