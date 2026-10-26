"""Exécution d'un cas du golden set de bout en bout via `/api/v1/interact`, puis comparaison des effets en base."""
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

from fastapi.testclient import TestClient

from app.core.database import DatabaseManager
from app.core.session_manager import get_session_manager
from tests.nlu_golden.models import FieldExpectations, GoldenCase

CASES_PATH = Path(__file__).with_name("cases.json")
CONTAINS_SUFFIX = "__contains"
# Colonnes techniques ignorées dans la comparaison avant/après.
VOLATILE_COLUMNS = {"created_at", "updated_at"}

Snapshot = Dict[int, Dict[str, Any]]


@dataclass
class CaseRun:
    today: date
    refs: Dict[str, int]
    before: Snapshot
    after: Snapshot
    responses: List[str]
    notes_delta: int


def snapshot_sessions(db: DatabaseManager) -> Snapshot:
    return {
        row["id"]: {k: v for k, v in row.items() if k not in VOLATILE_COLUMNS}
        for row in db.get_sport_sessions()
    }


def count_notes(db: DatabaseManager) -> int:
    with db.get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM second_brain_notes").fetchone()[0]


def run_case(case: GoldenCase, db: DatabaseManager, client: TestClient, today: date) -> CaseRun:
    """Insère le carnet, joue les tours de parole dans une même session, et capture l'état avant/après."""
    refs = {
        seed.ref: db.add_sport_session({
            **seed.model_dump(exclude={"ref", "day_offset"}, mode="json"),
            "date": (today + timedelta(days=seed.day_offset)).isoformat(),
        })
        for seed in case.carnet
    }
    before, notes_before = snapshot_sessions(db), count_notes(db)

    session_id = f"golden-{case.id}"
    responses = []
    try:
        for turn in case.turns:
            resp = client.post("/api/v1/interact", json={"query": turn, "session_id": session_id})
            assert resp.status_code == 200, f"[{case.id}] HTTP {resp.status_code} sur « {turn} » : {resp.text}"
            responses.append(resp.json()["spoken_response"])
    finally:
        get_session_manager().clear_session(session_id)

    return CaseRun(
        today=today,
        refs=refs,
        before=before,
        after=snapshot_sessions(db),
        responses=responses,
        notes_delta=count_notes(db) - notes_before,
    )


def _field_mismatches(row: Dict[str, Any], expected: FieldExpectations, today: date) -> List[str]:
    mismatches = []
    for key, want in expected.items():
        if key == "day_offset":
            want_date = (today + timedelta(days=int(want))).isoformat()
            if row["date"] != want_date:
                mismatches.append(f"date={row['date']!r} (attendu {want_date!r})")
        elif key.endswith(CONTAINS_SUFFIX):
            column = key.removesuffix(CONTAINS_SUFFIX)
            if str(want).lower() not in str(row.get(column) or "").lower():
                mismatches.append(f"{column}={row.get(column)!r} (doit contenir {want!r})")
        elif row.get(key) != want:
            mismatches.append(f"{key}={row.get(key)!r} (attendu {want!r})")
    return mismatches


def evaluate(case: GoldenCase, run: CaseRun) -> List[str]:
    """Retourne la liste des écarts entre l'effet observé et l'effet attendu (vide = cas réussi)."""
    expected = case.expected
    errors: List[str] = []
    ref_by_id = {session_id: ref for ref, session_id in run.refs.items()}

    for session_id, row_before in run.before.items():
        ref = ref_by_id.get(session_id, f"#{session_id}")
        row_after = run.after.get(session_id)
        if row_after is None:
            errors.append(f"séance '{ref}' supprimée")
        elif ref in expected.updated:
            errors += [f"séance '{ref}' : {m}" for m in _field_mismatches(row_after, expected.updated[ref], run.today)]
        elif row_after != row_before:
            changed = sorted(k for k in row_before if row_before[k] != row_after.get(k))
            errors.append(f"modification inattendue de la séance '{ref}' ({row_before['date']}) : {changed}")

    new_rows = [row for session_id, row in sorted(run.after.items()) if session_id not in run.before]
    if len(new_rows) != len(expected.created):
        summary = [(r["date"], r["type_seance"], r["statut"]) for r in new_rows]
        errors.append(f"{len(new_rows)} séance(s) créée(s) {summary}, {len(expected.created)} attendue(s)")
    else:
        for row, want in zip(new_rows, expected.created):
            errors += [f"séance créée : {m}" for m in _field_mismatches(row, want, run.today)]

    last_response = run.responses[-1] if run.responses else ""
    if expected.clarification and "?" not in last_response:
        errors.append(f"clarification attendue, réponse obtenue : « {last_response} »")
    if expected.notes_created is not None and run.notes_delta != expected.notes_created:
        errors.append(f"{run.notes_delta} note(s) créée(s), {expected.notes_created} attendue(s)")
    for word in expected.response_excludes:
        if word.lower() in last_response.lower():
            errors.append(f"la réponse ne doit pas contenir « {word} » : « {last_response} »")
    return errors
