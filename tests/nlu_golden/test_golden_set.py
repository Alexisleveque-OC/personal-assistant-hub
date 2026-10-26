"""Jeu de référence NLU (golden set) : phrase(s) réelles réécrites → effet attendu sur le carnet sportif.

Mode mesuré : pipeline actuel `/interact` (regex `IntentParser` + handlers), Gemini désactivé
pour rester déterministe et hors-ligne. Les cas en échec sont marqués `xfail(strict=True)` :
ce sont les cibles de la Phase 6.8 ; dès qu'un cas passe, le marqueur doit être retiré.
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

# Échecs du pipeline legacy mesurés à l'Étape 0 (cibles à faire passer au vert).
LEGACY_FAILURES: dict[str, str] = {
    "correction-suivi-renfo": "La précision au tour suivant n'est pas comprise (« je n'ai pas bien compris »).",
    "type-corrige-seance-du-jour": "Ciblage par type : modifie l'ancien fractionné au lieu de la séance du jour.",
    "rpe-du-jour-malgre-mention-renfo": "La simple mention du renfo détourne la modification vers celui-ci.",
    "planifie-sortie-longue-demain": "Répond « sortie longue » mais enregistre une séance EF.",
    "ajoute-seance-pas-aux-courses": "Classé comme article de courses par la voie rapide « ajoute X ».",
    "annule-derniere-modification": "Les modifications de séance ne sont pas annulables.",
    "annule-et-note-correctif": "Phrase composée non comprise : enregistre une séance au lieu d'annuler et noter.",
    "note-sur-echanges-precedents": "Prise de note sur référence à l'historique non comprise.",
    "clarification-deux-seances-meme-jour": "Devine une séance au lieu de demander laquelle.",
    "aucune-seance-du-jour": "Crée une séance et affirme l'avoir « mise à jour » au lieu de signaler l'absence.",
}


def _params():
    for case in CASES:
        marks = []
        if case.id in LEGACY_FAILURES:
            marks.append(pytest.mark.xfail(strict=True, reason=LEGACY_FAILURES[case.id]))
        yield pytest.param(case, id=case.id, marks=marks)


def test_case_ids_are_unique():
    ids = [c.id for c in CASES]
    assert len(ids) == len(set(ids))
    assert set(LEGACY_FAILURES) <= set(ids), f"xfail sans cas : {set(LEGACY_FAILURES) - set(ids)}"


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
