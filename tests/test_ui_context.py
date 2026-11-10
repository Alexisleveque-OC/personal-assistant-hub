"""Refonte UX (ROADMAP Étape 0) : la feuille ouverte (Courses, Repas…) est transmise à Otis (`ui_context`),
en texte comme en audio, et l'agent en tient compte pour lever les ambiguïtés."""
import io
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.agent_service import AgentReply, AgentService
from app.core.agent.prompt import build_system_prompt
from app.core.agent.tools.sport_registry import build_sport_registry
from app.core.agent.tools.sport_tools import SportTools
from app.core.models import IntentType
from app.core.session_manager import get_session_manager
from app.core.audio.stt_service import set_stt_service
from app.handlers import agent_handler
from app.main import app
from tests.agent_fakes import ScriptedLLM, text_turn

TODAY = date(2026, 11, 10)


@pytest.mark.parametrize("ui_context, label", [
    ("courses", "Courses"),
    ("repas", "Repas"),
    ("taches", "Tâches"),
    ("sport", "Sport"),
    ("second_cerveau", "Second cerveau"),
])
def test_prompt_names_the_open_screen_and_asks_to_favour_its_domain(ui_context, label):
    prompt = build_system_prompt(TODAY, [], ui_context=ui_context)

    assert f"Écran ouvert : {label}" in prompt
    assert "privilégie ce domaine" in prompt


@pytest.mark.parametrize("ui_context", [None, "", "accueil", "inconnu"])
def test_prompt_has_no_screen_line_from_home_or_an_unknown_screen(ui_context):
    assert "Écran ouvert" not in build_system_prompt(TODAY, [], ui_context=ui_context)


@pytest.mark.asyncio
async def test_agent_run_puts_the_open_screen_in_the_system_instruction(isolate_sqlite_database):
    tools = SportTools(SqlSportConnector(db_manager=isolate_sqlite_database), today=lambda: TODAY)
    llm = ScriptedLLM([text_turn("C'est noté.")])
    service = AgentService(llm=llm, registry=build_sport_registry(tools), sport_tools=tools)

    await service.run("le vélo de Manon", ui_context="second_cerveau")

    assert "Écran ouvert : Second cerveau" in llm.requests[0]["system_instruction"]


@pytest.mark.asyncio
async def test_agent_turn_forwards_the_session_screen_to_the_agent(monkeypatch):
    captured = {}

    async def fake_run(query, history=(), ui_context=None, ui_session_id=None):
        captured["ui_context"] = ui_context
        return AgentReply(text="Ok", executions=[])

    monkeypatch.setattr(
        agent_handler, "build_agent_service", lambda *a, **k: SimpleNamespace(run=fake_run, llm=None),
    )
    session_ctx = {"ui_context": "courses"}

    await agent_handler.handle_agent_turn("ajoute des pommes", "s-ui", session_ctx, sport_connector=None)

    assert captured["ui_context"] == "courses"


def _mock_stt(text: str):
    parsed = MagicMock()
    parsed.intent = IntentType.UNKNOWN
    parsed.parameters = {}
    parsed.confidence = 0.0
    parsed.conversational_reply = None
    parsed.raw_query = text
    stt = MagicMock()
    stt.process_audio = AsyncMock(return_value=(text, parsed))
    return stt


def test_audio_interaction_stores_the_screen_context_in_the_session():
    set_stt_service(_mock_stt("bonjour"))
    try:
        resp = TestClient(app).post(
            "/api/v1/interact/audio",
            files={"audio_file": ("cmd.ogg", io.BytesIO(b"MOCK_AUDIO"), "audio/ogg")},
            data={"session_id": "audio-ui-ctx", "context": '{"ui_context": "courses"}'},
        )
    finally:
        set_stt_service(None)

    assert resp.status_code == 200, resp.text
    assert get_session_manager().get_session("audio-ui-ctx").get("ui_context") == "courses"


def test_audio_interaction_rejects_a_context_that_is_not_a_json_object():
    resp = TestClient(app).post(
        "/api/v1/interact/audio",
        files={"audio_file": ("cmd.ogg", io.BytesIO(b"MOCK_AUDIO"), "audio/ogg")},
        data={"session_id": "audio-ui-bad", "context": "courses"},
    )

    assert resp.status_code == 422
    assert "context" in resp.json()["detail"]


# ---------- Détail d'une séance : la séance ouverte est signalée à Otis (décision du 10/11) ----------

def _open_view():
    from app.core.agent.tools.sport_models import SessionView
    return SessionView(id=16, date=date(2026, 11, 9), jour="lundi", statut="Réalisé", type_seance="Sortie Longue",
                       distance_km=7.01)


def test_prompt_names_the_open_session_and_makes_it_the_default_target():
    prompt = build_system_prompt(TODAY, [], ui_context="sport", open_session=_open_view())

    assert "Séance ouverte à l'écran : - id=16" in prompt
    assert "porte sur cette séance, même si une séance plus récente existe" in prompt


@pytest.mark.asyncio
async def test_agent_run_looks_up_the_open_session(isolate_sqlite_database):
    db = isolate_sqlite_database
    session_id = db.add_sport_session({"date": "2026-11-09", "type_seance": "Sortie Longue", "statut": "Réalisé"})
    tools = SportTools(SqlSportConnector(db_manager=db), today=lambda: TODAY)
    llm = ScriptedLLM([text_turn("Ok"), text_turn("Ok")])
    service = AgentService(llm=llm, registry=build_sport_registry(tools), sport_tools=tools)

    await service.run("c'était 48 minutes", ui_context="sport", ui_session_id=session_id)
    await service.run("c'était 48 minutes", ui_context="sport", ui_session_id=99999)  # supprimée entre-temps

    assert f"Séance ouverte à l'écran : - id={session_id}" in llm.requests[0]["system_instruction"]
    assert "Séance ouverte" not in llm.requests[1]["system_instruction"]


@pytest.mark.asyncio
async def test_agent_turn_forwards_the_open_session(monkeypatch):
    captured = {}

    async def fake_run(query, history=(), ui_context=None, ui_session_id=None):
        captured.update(ui_context=ui_context, ui_session_id=ui_session_id)
        return AgentReply(text="Ok", executions=[])

    monkeypatch.setattr(
        agent_handler, "build_agent_service", lambda *a, **k: SimpleNamespace(run=fake_run, llm=None),
    )

    await agent_handler.handle_agent_turn(
        "c'était 48 minutes", "s-ui", {"ui_context": "sport", "ui_session_id": 16}, sport_connector=None,
    )

    assert captured == {"ui_context": "sport", "ui_session_id": 16}
