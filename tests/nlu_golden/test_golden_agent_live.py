"""Évaluation RÉELLE du golden set en mode agent contre Gemini (hors CI : quota et non-déterminisme).

Lancement : RUN_LIVE_GEMINI=1 .venv/bin/pytest tests/nlu_golden/test_golden_agent_live.py -v -rxX
"""
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.factory import set_agent_llm
from app.core.agent.llm import GeminiAgentLLM
from app.core.clock import paris_today
from app.core.dependencies import set_sport_connector
from app.core.llm.gemini_client import GeminiClient
from app.main import app
from tests.nlu_golden.models import GoldenCase
from tests.nlu_golden.runner import evaluate, run_case
from tests.nlu_golden.test_golden_set import CASES

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_GEMINI") != "1", reason="Évaluation réelle Gemini : définir RUN_LIVE_GEMINI=1."
)

# Capacités prévues aux étapes suivantes : échecs attendus (non stricts, le LLM n'est pas déterministe).
AGENT_PENDING: dict[str, str] = {
    "annule-derniere-modification": "Annulation fiable : Étape 4.",
    "annule-et-note-correctif": "Annulation fiable : Étape 4.",
}


def _params():
    for case in CASES:
        marks = [pytest.mark.xfail(strict=False, reason=AGENT_PENDING[case.id])] if case.id in AGENT_PENDING else []
        yield pytest.param(case, id=case.id, marks=marks)


@pytest.mark.parametrize("case", _params())
def test_golden_case_agent_live(case: GoldenCase, isolate_sqlite_database, monkeypatch):
    api_key = settings.gemini_api_key.strip()
    assert api_key, "GEMINI_API_KEY absente du .env : impossible d'évaluer l'agent réel."
    monkeypatch.setattr(settings, "nlu_mode", "agent")
    set_sport_connector(SqlSportConnector(db_manager=isolate_sqlite_database))
    set_agent_llm(GeminiAgentLLM(GeminiClient(api_key=api_key, timeout=20.0)))
    try:
        with patch("app.main.get_nlu_service", return_value=None), \
             patch("app.routers.interact.get_nlu_service", return_value=None):
            # L'agent raisonne à l'heure de Paris : le carnet doit être daté avec la même horloge.
            run = run_case(case, isolate_sqlite_database, TestClient(app), today=paris_today())
    finally:
        set_sport_connector(None)
        set_agent_llm(None)

    errors = evaluate(case, run)
    assert not errors, f"[{case.id}] réponses {run.responses}\n  - " + "\n  - ".join(errors)
