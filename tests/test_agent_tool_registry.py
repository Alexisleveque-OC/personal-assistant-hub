"""Tests du registre d'outils de l'agent et du branchement des outils sport."""
from datetime import date

import pytest

from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.tool_registry import AgentTool, ToolRegistry
from app.core.agent.tools.sport_models import GetSessionArgs
from app.core.agent.tools.sport_registry import build_sport_registry
from app.core.agent.tools.sport_tools import SportTools

TODAY = date(2026, 10, 19)
SPORT_TOOL_NAMES = [
    "find_sport_sessions", "get_sport_session", "update_sport_session", "log_sport_session", "plan_sport_session",
]


@pytest.fixture
def db(isolate_sqlite_database):
    return isolate_sqlite_database


@pytest.fixture
def registry(db):
    return build_sport_registry(SportTools(SqlSportConnector(db_manager=db), today=lambda: TODAY))


def test_declarations_expose_all_sport_tools_with_schemas(registry):
    declarations = registry.declarations()
    assert [d["name"] for d in declarations] == SPORT_TOOL_NAMES
    for decl in declarations:
        assert decl["description"]
        assert decl["parameters"]["type"] == "object"


def test_duplicate_tool_names_are_rejected():
    tool = AgentTool(name="x", description="d", args_model=GetSessionArgs, handler=lambda a: a)
    with pytest.raises(ValueError, match="x"):
        ToolRegistry([tool, tool])


@pytest.mark.asyncio
async def test_find_returns_sessions_payload(db, registry):
    session_id = db.add_sport_session({"date": "2026-10-18", "type_seance": "EF", "statut": "Réalisé"})
    execution = await registry.execute("find_sport_sessions", {"limit": 5})
    assert execution.error is None
    assert execution.response["sessions"][0]["id"] == session_id
    assert execution.response["sessions"][0]["date"] == "2026-10-18"
    assert execution.undos == []


@pytest.mark.asyncio
async def test_mutation_returns_session_and_keeps_undo_snapshot(db, registry):
    session_id = db.add_sport_session({"date": "2026-10-19", "type_seance": "EF", "statut": "Réalisé"})
    execution = await registry.execute("update_sport_session", {"session_id": session_id, "changes": {"ressenti_rpe": 5}})
    assert execution.error is None
    assert execution.response == {"action": "updated", "session": execution.response["session"]}
    assert execution.response["session"]["ressenti_rpe"] == 5
    assert len(execution.undos) == 1 and execution.undos[0].before.ressenti_rpe is None


@pytest.mark.asyncio
async def test_business_error_is_returned_to_the_model(registry):
    execution = await registry.execute("get_sport_session", {"session_id": 404})
    assert execution.response == {"error": execution.error}
    assert "404" in execution.error


@pytest.mark.asyncio
async def test_invalid_arguments_are_returned_as_explicit_error(registry):
    execution = await registry.execute("update_sport_session", {"session_id": 1, "changes": {"ressenti_rpe": 15}})
    assert "ressenti_rpe" in execution.error


@pytest.mark.asyncio
async def test_unknown_tool_lists_available_tools(registry):
    execution = await registry.execute("delete_everything", {})
    assert "delete_everything" in execution.error
    assert "find_sport_sessions" in execution.error


def test_tool_without_arguments_omits_parameters():
    """Gemini refuse un objet sans propriétés : un outil sans argument ne déclare pas de `parameters`."""
    from app.core.agent.tools.undo_tools import UndoLastActionArgs
    tool = AgentTool(name="noop", description="d", args_model=UndoLastActionArgs, handler=lambda a: a)
    assert tool.declaration() == {"name": "noop", "description": "d"}
