"""Exécution d'un cas du golden set de bout en bout via `/api/v1/interact`, puis comparaison des effets
en base (carnet sport, notes) et dans le classeur Repas & Courses (doublure en mémoire)."""
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
import re
from typing import Any, Dict, List, Tuple
import unicodedata

from fastapi.testclient import TestClient

from app.connectors.sheets.meals_connector import MealsShoppingConnector
from app.core.database import DatabaseManager
from app.core.dependencies import set_meals_connector
from app.core.session_manager import get_session_manager
from tests.meals_fakes import (
    MealsSheetState,
    WeekItem,
    build_meals_spreadsheet,
    planned_meals,
    waiting_rows,
    week_rows,
)
from tests.nlu_golden.models import FieldExpectations, GoldenCase

CASES_PATH = Path(__file__).with_name("cases.json")
CONTAINS_SUFFIX = "__contains"
# Colonnes techniques ignorées dans la comparaison avant/après.
VOLATILE_COLUMNS = {"created_at", "updated_at"}

Snapshot = Dict[int, Dict[str, Any]]
ShoppingRow = Tuple[str, str, bool]  # (liste « attente »/« semaine », nom, coché)
MealsPlan = Dict[str, Tuple[str, str]]  # « JJ/MM/AAAA » → (midi, soir)
RayonRow = Tuple[str, str]  # ligne de Ingredients_Rayons : (article, rayon)

_FRENCH_WORDS = {"le", "la", "les", "de", "des", "du", "un", "une", "est", "et", "à", "pour", "pas", "que", "qui",
                 "il", "faut", "sur", "au", "a", "été", "ma", "mon", "ce", "en"}
_ENGLISH_WORDS = {"the", "and", "is", "was", "to", "of", "should", "for", "on", "with", "this", "that", "it", "be"}


@dataclass
class CaseRun:
    today: date
    refs: Dict[str, int]
    before: Snapshot
    after: Snapshot
    responses: List[str]
    notes_delta: int
    courses_before: List[ShoppingRow] = field(default_factory=list)
    courses_after: List[ShoppingRow] = field(default_factory=list)
    meals_before: MealsPlan = field(default_factory=dict)
    meals_after: MealsPlan = field(default_factory=dict)
    new_notes: List[str] = field(default_factory=list)
    rayons_before: List[RayonRow] = field(default_factory=list)
    rayons_after: List[RayonRow] = field(default_factory=list)


def snapshot_sessions(db: DatabaseManager) -> Snapshot:
    return {
        row["id"]: {k: v for k, v in row.items() if k not in VOLATILE_COLUMNS}
        for row in db.get_sport_sessions()
    }


def count_notes(db: DatabaseManager) -> int:
    with db.get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM second_brain_notes").fetchone()[0]


def _last_note_id(db: DatabaseManager) -> int:
    with db.get_connection() as conn:
        return conn.execute("SELECT COALESCE(MAX(id), 0) FROM second_brain_notes").fetchone()[0]


def _notes_after(db: DatabaseManager, note_id: int) -> List[str]:
    with db.get_connection() as conn:
        rows = conn.execute("SELECT content FROM second_brain_notes WHERE id > ? ORDER BY id", (note_id,)).fetchall()
    return [row[0] for row in rows]


def _build_sheet(case: GoldenCase, today: date):
    return build_meals_spreadsheet(MealsSheetState(
        today=today,
        waiting=[(item.nom, item.coche) for item in case.courses if item.liste == "attente"],
        week=[WeekItem(item.nom, item.rayon, item.coche) for item in case.courses if item.liste == "semaine"],
        meals={today + timedelta(days=meal.day_offset): (meal.midi, meal.soir) for meal in case.repas},
    ))


def _shopping(sheet) -> List[ShoppingRow]:
    return [("attente", n, c) for n, c in waiting_rows(sheet)] + [("semaine", n, c) for n, c in week_rows(sheet)]


def run_case(case: GoldenCase, db: DatabaseManager, client: TestClient, today: date) -> CaseRun:
    """Insère le carnet, joue les tours de parole dans une même session, et capture l'état avant/après."""
    refs = {
        seed.ref: db.add_sport_session({
            **seed.model_dump(exclude={"ref", "day_offset"}, mode="json"),
            "date": (today + timedelta(days=seed.day_offset)).isoformat(),
        })
        for seed in case.carnet
    }
    sheet = _build_sheet(case, today)
    set_meals_connector(MealsShoppingConnector(spreadsheet=sheet))
    before, notes_before, last_note = snapshot_sessions(db), count_notes(db), _last_note_id(db)
    courses_before, meals_before, rayons_before = _shopping(sheet), planned_meals(sheet), _rayons(sheet)

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
        courses_before=courses_before,
        courses_after=_shopping(sheet),
        meals_before=meals_before,
        meals_after=planned_meals(sheet),
        new_notes=_notes_after(db, last_note),
        rayons_before=rayons_before,
        rayons_after=_rayons(sheet),
    )


def _rayons(sheet) -> List[RayonRow]:
    return [(row[0], row[1] if len(row) > 1 else "") for row in sheet.worksheet("Ingredients_Rayons").get_all_values()[1:]]


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

    errors += _shopping_mismatches(case, run)
    errors += _meal_mismatches(case, run)
    errors += _rayon_mismatches(case, run)

    last_response = run.responses[-1] if run.responses else ""
    if expected.clarification and "?" not in last_response:
        errors.append(f"clarification attendue, réponse obtenue : « {last_response} »")
    if expected.notes_created is not None and run.notes_delta != expected.notes_created:
        errors.append(f"{run.notes_delta} note(s) créée(s), {expected.notes_created} attendue(s)")
    if expected.notes_francais:
        errors += [f"note non rédigée en français : « {note} »" for note in run.new_notes if not _is_french(note)]
    for word in expected.notes_contiennent:
        errors += [f"la note doit contenir « {word} » : « {note} »" for note in run.new_notes if word.lower() not in note.lower()]
    for word in expected.response_includes:
        if word.lower() not in last_response.lower():
            errors.append(f"la réponse doit contenir « {word} » : « {last_response} »")
    for word in expected.response_excludes:
        if word.lower() in last_response.lower():
            errors.append(f"la réponse ne doit pas contenir « {word} » : « {last_response} »")
    return errors


def item_key(name: str) -> str:
    """Clé de comparaison d'un article : sans casse, accents, article initial ni pluriel simple."""
    text = unicodedata.normalize("NFKD", name.casefold().replace("œ", "oe"))
    text = "".join(c for c in text if not unicodedata.combining(c)).strip()
    text = re.sub(r"^(?:du|de la|des|de l'|d'|le|la|les|l'|un|une)\s*", "", text)
    return " ".join(w[:-1] if len(w) > 3 and w[-1] in "sx" else w for w in text.split())


def _shopping_mismatches(case: GoldenCase, run: CaseRun) -> List[str]:
    expected = case.expected
    names = {(liste, item_key(nom)): nom for liste, nom, _ in run.courses_before + run.courses_after}
    before = Counter((liste, item_key(nom)) for liste, nom, _ in run.courses_before)
    after = Counter((liste, item_key(nom)) for liste, nom, _ in run.courses_after)
    errors: List[str] = []
    for label, observed, wanted in (
        ("ajouté(s)", after - before, Counter(("attente", item_key(n)) for n in expected.courses_ajoutees)),
        ("retiré(s)", before - after, Counter(("attente", item_key(n)) for n in expected.courses_retirees)),
    ):
        if observed != wanted:
            errors.append(
                f"article(s) {label} : {sorted(names[k] for k in observed.elements())}, "
                f"attendu(s) : {sorted(k[1] for k in wanted.elements())}"
            )

    state_before = {(liste, item_key(nom)): coche for liste, nom, coche in run.courses_before}
    state_after = {(liste, item_key(nom)): coche for liste, nom, coche in run.courses_after}
    flipped = {key: state_after[key] for key in state_before.keys() & state_after.keys() if state_before[key] != state_after[key]}
    checked = {key[1] for key, coche in flipped.items() if coche}
    unexpected = sorted(names[key] for key, coche in flipped.items() if not coche or key[1] not in map(item_key, expected.courses_cochees))
    if unexpected:
        errors.append(f"état coché modifié de façon inattendue : {unexpected}")
    missing = sorted(n for n in expected.courses_cochees if item_key(n) not in checked)
    if missing:
        errors.append(f"article(s) non coché(s) : {missing}")
    return errors


def _rayon_mismatches(case: GoldenCase, run: CaseRun) -> List[str]:
    """Rayons appris (lignes ajoutées à Ingredients_Rayons), comparés article par article."""
    added = Counter((item_key(name), rayon) for name, rayon in run.rayons_after) - Counter(
        (item_key(name), rayon) for name, rayon in run.rayons_before
    )
    wanted = Counter((item_key(name), rayon) for name, rayon in case.expected.rayons_appris.items())
    if added == wanted:
        return []
    names = {item_key(name): name for name, _ in run.rayons_after}
    return [
        f"rayon(s) appris : {sorted((names[k], r) for k, r in added.elements())}, "
        f"attendu(s) : {sorted(case.expected.rayons_appris.items())}"
    ]


def _meal_mismatches(case: GoldenCase, run: CaseRun) -> List[str]:
    wanted = {
        ((run.today + timedelta(days=m.day_offset)).strftime("%d/%m/%Y"), m.moment): m.plat__contains
        for m in case.expected.repas_modifies
    }
    errors: List[str] = []
    for day in sorted(run.meals_before.keys() | run.meals_after.keys()):
        before, after = run.meals_before.get(day, ("", "")), run.meals_after.get(day, ("", ""))
        for index, moment in enumerate(("midi", "soir")):
            target = wanted.pop((day, moment), None)
            if target is not None:
                if target.lower() not in after[index].lower():
                    errors.append(f"repas du {day} {moment} : « {after[index]} » (doit contenir « {target} »)")
            elif before[index] != after[index]:
                errors.append(f"repas du {day} {moment} modifié de façon inattendue : « {before[index]} » → « {after[index]} »")
    errors += [f"repas du {day} {moment} absent du planning" for day, moment in wanted]
    return errors


def _is_french(text: str) -> bool:
    words = re.findall(r"[a-zà-ÿ]+", text.lower())
    return sum(w in _FRENCH_WORDS for w in words) > sum(w in _ENGLISH_WORDS for w in words)
