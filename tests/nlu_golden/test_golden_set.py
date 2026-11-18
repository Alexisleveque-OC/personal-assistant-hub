"""Jeu de référence NLU (golden set) : phrase(s) réelles réécrites → effet attendu sur le carnet sportif.

Mode mesuré : pipeline legacy `/interact` (regex `IntentParser` + handlers), Gemini désactivé
pour rester déterministe et hors-ligne. La prod est en mode agent : les cas que le pipeline legacy ne sait pas
traiter (LEGACY_UNSUPPORTED) ne sont mesurés que par test_golden_agent_live.py (RUN_LIVE_GEMINI=1).
"""
import json
from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.dependencies import set_sport_connector
from app.main import app
from tests.nlu_golden.models import GoldenCase
from tests.nlu_golden.runner import CASES_PATH, evaluate, run_case

CASES = [GoldenCase.model_validate(raw) for raw in json.loads(CASES_PATH.read_text(encoding="utf-8"))]

LEGACY_UNSUPPORTED = {
    "correction-suivi-renfo",
    "type-corrige-seance-du-jour",
    "rpe-du-jour-malgre-mention-renfo",
    "planifie-sortie-longue-demain",
    "ajoute-seance-pas-aux-courses",
    "annule-derniere-modification",
    "annule-et-note-correctif",
    "note-sur-echanges-precedents",
    "clarification-deux-seances-meme-jour",
    "aucune-seance-du-jour",
    "courses-ajout-rayon-explicite",
    "courses-ajout-repas-pas-aux-courses",
    "courses-coche-articles",
    "courses-retire-article",
    "courses-coche-et-ajoute",
    "repas-midi-et-soir",
    "repas-change-plat-demain",
}


def _params():
    return [pytest.param(case, id=case.id) for case in CASES if case.id not in LEGACY_UNSUPPORTED]


def test_case_ids_are_unique():
    ids = [c.id for c in CASES]
    assert len(ids) == len(set(ids))
    assert LEGACY_UNSUPPORTED <= set(ids), f"cas exclus inconnus : {LEGACY_UNSUPPORTED - set(ids)}"


@pytest.mark.parametrize("case", _params())
def test_golden_case(case: GoldenCase, isolate_sqlite_database):
    set_sport_connector(SqlSportConnector(db_manager=isolate_sqlite_database))
    try:
        # Même horloge que le code legacy (`date.today()`), sinon carnet et parser divergent autour de minuit.
        with patch("app.main.get_nlu_service", return_value=None), \
             patch("app.routers.interact.get_nlu_service", return_value=None):
            run = run_case(case, isolate_sqlite_database, TestClient(app), today=date.today())
    finally:
        set_sport_connector(None)

    errors = evaluate(case, run)
    assert not errors, f"[{case.id}] « {case.turns[-1]} » → réponses {run.responses}\n  - " + "\n  - ".join(errors)
