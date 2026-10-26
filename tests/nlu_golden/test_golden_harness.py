"""Tests du harnais du golden set : l'instrument de mesure ne doit jamais être faussement vert."""
from datetime import date

import pytest
from pydantic import ValidationError

from tests.nlu_golden.models import GoldenCase
from tests.nlu_golden.runner import CaseRun, evaluate

TODAY = date(2026, 10, 19)


def _row(session_id: int, day: str, type_seance: str = "EF", rpe=None) -> dict:
    return {"id": session_id, "date": day, "type_seance": type_seance, "statut": "Réalisé", "ressenti_rpe": rpe, "remarques": ""}


def _case(expected: dict, turns=("RPE à 3",)) -> GoldenCase:
    return GoldenCase.model_validate({
        "id": "cas-test",
        "origine": "test du harnais",
        "carnet": [
            {"ref": "renfo", "day_offset": -3, "type_seance": "Renforcement"},
            {"ref": "du_jour", "day_offset": 0, "type_seance": "EF"},
        ],
        "turns": list(turns),
        "expected": expected,
    })


def _run(after_rows, responses=("C'est noté.",), notes_delta=0) -> CaseRun:
    before = {1: _row(1, "2026-10-16", "Renforcement"), 2: _row(2, "2026-10-19")}
    return CaseRun(
        today=TODAY,
        refs={"renfo": 1, "du_jour": 2},
        before=before,
        after={r["id"]: r for r in after_rows},
        responses=list(responses),
        notes_delta=notes_delta,
    )


def test_expected_update_on_target_passes():
    case = _case({"updated": {"renfo": {"ressenti_rpe": 3}}})
    run = _run([_row(1, "2026-10-16", "Renforcement", rpe=3), _row(2, "2026-10-19")])
    assert evaluate(case, run) == []


def test_wrong_session_modified_is_reported():
    case = _case({"updated": {"renfo": {"ressenti_rpe": 3}}})
    run = _run([_row(1, "2026-10-16", "Renforcement"), _row(2, "2026-10-19", rpe=3)])
    errors = evaluate(case, run)
    assert any("renfo" in e and "ressenti_rpe" in e for e in errors)
    assert any("du_jour" in e and "inattendue" in e for e in errors)


def test_unexpected_creation_and_deletion_are_reported():
    case = _case({})
    run = _run([_row(2, "2026-10-19"), _row(3, "2026-10-19", "Fractionné")])
    errors = evaluate(case, run)
    assert any("supprimée" in e for e in errors)
    assert any("créée" in e for e in errors)


def test_created_session_matches_with_day_offset_and_contains():
    case = _case({"created": [{"type_seance": "Fractionné", "day_offset": 0, "remarques__contains": "souffle"}]})
    created = _row(3, "2026-10-19", "Fractionné") | {"remarques": "Le SOUFFLE court"}
    run = _run([_row(1, "2026-10-16", "Renforcement"), _row(2, "2026-10-19"), created])
    assert evaluate(case, run) == []


def test_clarification_requires_a_question_and_no_mutation():
    case = _case({"clarification": True})
    untouched = [_row(1, "2026-10-16", "Renforcement"), _row(2, "2026-10-19")]
    assert evaluate(case, _run(untouched, responses=("Tu parles de laquelle ?",))) == []
    assert evaluate(case, _run(untouched, responses=("C'est noté.",))) != []


def test_notes_count_and_forbidden_words_are_checked():
    case = _case({"notes_created": 1, "response_excludes": ["renforcement"]})
    untouched = [_row(1, "2026-10-16", "Renforcement"), _row(2, "2026-10-19")]
    errors = evaluate(case, _run(untouched, responses=("Séance de Renforcement enregistrée",), notes_delta=0))
    assert len(errors) == 2


def test_clarification_case_cannot_expect_mutation():
    with pytest.raises(ValidationError, match="clarification"):
        _case({"clarification": True, "updated": {"renfo": {"ressenti_rpe": 3}}})


def test_unknown_ref_in_expectation_is_rejected():
    with pytest.raises(ValidationError, match="absentes du carnet"):
        _case({"updated": {"inconnue": {"ressenti_rpe": 3}}})
