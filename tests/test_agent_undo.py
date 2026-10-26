"""Tests de l'annulation fiable de l'agent (Phase 6.8 - Étape 4) : journal SQLite persistant et restauration exacte."""
from datetime import date

import pytest

from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.tools.sport_models import LogSessionArgs, SessionChanges, UpdateSessionArgs
from app.core.agent.tools.sport_tools import SportToolError, SportTools
from app.core.agent.undo import NoteUndo, UndoError, UndoJournal, UndoService

TODAY = date(2026, 10, 19)
VOLATILE = {"created_at", "updated_at"}


@pytest.fixture
def db(isolate_sqlite_database):
    return isolate_sqlite_database


@pytest.fixture
def tools(db):
    return SportTools(SqlSportConnector(db_manager=db), today=lambda: TODAY)


@pytest.fixture
def journal(db):
    return UndoJournal(db)


@pytest.fixture
def service(db, tools, journal):
    return UndoService(sport_tools=tools, db=db, journal=journal)


def _row(db, session_id):
    return {k: v for k, v in db.get_sport_session_by_id(session_id).items() if k not in VOLATILE}


def _update(tools, session_id, **changes):
    return tools.update_sport_session(UpdateSessionArgs(session_id=session_id, changes=SessionChanges(**changes))).undo


def test_journal_persists_batches_per_session_and_skips_empty(db, journal, tools):
    session_id = db.add_sport_session({"date": "2026-10-19", "type_seance": "EF", "statut": "Réalisé"})
    undo = _update(tools, session_id, ressenti_rpe=5)

    assert journal.record("s1", []) is None
    batch_id = journal.record("s1", [undo, NoteUndo(note_id=3)])

    reloaded = UndoJournal(db).last("s1")  # nouvelle instance : rien n'est gardé en mémoire
    assert reloaded.id == batch_id
    assert reloaded.undos[0].session_id == session_id
    assert reloaded.undos[1] == NoteUndo(note_id=3)
    assert UndoJournal(db).last("autre-session") is None


def test_undo_restores_batch_in_reverse_order_and_marks_it_done(db, tools, journal, service):
    session_id = db.add_sport_session({"date": "2026-10-19", "type_seance": "EF", "statut": "Réalisé"})
    original = _row(db, session_id)
    first = _update(tools, session_id, ressenti_rpe=5)
    second = _update(tools, session_id, ressenti_rpe=6, type_seance="Fractionné")
    created = tools.log_sport_session(LogSessionArgs(date=TODAY, type_seance="Renforcement"))
    journal.record("s1", [first, second, created.undo])

    outcome = service.undo_last("s1")

    assert _row(db, session_id) == original
    assert db.get_sport_session_by_id(created.session.id) is None
    assert outcome.restored == [
        "séance Renforcement du 19/10 supprimée",
        "séance Fractionné du 19/10 restaurée",
        "séance EF du 19/10 restaurée",
    ]
    assert journal.last("s1") is None


def test_undo_takes_the_previous_batch_next_time(db, tools, journal, service):
    session_id = db.add_sport_session({"date": "2026-10-19", "type_seance": "EF", "statut": "Réalisé"})
    journal.record("s1", [_update(tools, session_id, ressenti_rpe=4)])
    journal.record("s1", [_update(tools, session_id, meteo_note=3)])

    service.undo_last("s1")
    assert (db.get_sport_session_by_id(session_id)["ressenti_rpe"], db.get_sport_session_by_id(session_id)["meteo_note"]) == (4, None)
    service.undo_last("s1")
    assert db.get_sport_session_by_id(session_id)["ressenti_rpe"] is None


def test_undo_refuses_when_session_changed_since_and_applies_nothing(db, tools, journal, service):
    edited = db.add_sport_session({"date": "2026-10-19", "type_seance": "EF", "statut": "Réalisé"})
    other = db.add_sport_session({"date": "2026-10-18", "type_seance": "Renforcement", "statut": "Réalisé"})
    batch = [_update(tools, other, ressenti_rpe=3), _update(tools, edited, ressenti_rpe=5)]
    journal.record("s1", batch)
    db.update_sport_session(edited, {"remarques": "Corrigé à la main"})  # modification ultérieure (éditeur, import…)

    with pytest.raises(UndoError, match="modifiée depuis"):
        service.undo_last("s1")

    assert db.get_sport_session_by_id(other)["ressenti_rpe"] == 3  # tout ou rien
    assert journal.last("s1") is not None


def test_undo_deletes_note_created_by_agent(db, journal, service):
    note_id = db.add_note(category="thought", content="Idée")
    journal.record("s1", [NoteUndo(note_id=note_id)])
    outcome = service.undo_last("s1")
    assert db.get_note(note_id) is None
    assert outcome.restored == ["note « Idée » supprimée"]


def test_nothing_to_undo_raises_explicit_error(service):
    with pytest.raises(UndoError, match="Aucune action"):
        service.undo_last("vide")


def test_undo_error_is_a_tool_error_returned_to_the_model():
    assert issubclass(UndoError, SportToolError)
