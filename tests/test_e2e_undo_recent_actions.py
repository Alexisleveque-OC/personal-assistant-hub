"""E2E (vrai Chromium) : « Annuler » sur une action plus ancienne de « Dernières actions » (ROADMAP undo, étape 6).

La base du serveur isolé est pré-remplie comme après deux échanges avec Otis faits depuis ce téléphone :
une note (annulable) puis une note plus récente. Aucun appel Google ni Gemini.
"""
import json

import pytest

from app.core.database import DatabaseManager
from tests.test_e2e_navigation import base_url, browser, e2e_server, page  # noqa: F401 (fixtures)

SESSION = "e2e-phone"


def _note_action(db: DatabaseManager, content: str) -> int:
    note_id = db.add_note(content=content, category="thought")
    batch_id = db.add_agent_undo_batch(SESSION, json.dumps([{"kind": "note", "note_id": note_id}]))
    db.log_conversation(
        raw_query=f"Note {content}", intent="agent", spoken_response="C'est noté.", session_id=SESSION,
        parameters={"tool_calls": [{"name": "save_note", "args": {"category": "thought"}, "error": None}],
                    "undo_batch_id": batch_id},
    )
    return note_id


@pytest.fixture
def two_notes(e2e_server):
    db = DatabaseManager(db_path=str(e2e_server[1]))
    older = _note_action(db, "Penser aux piles")
    newer = _note_action(db, "Rappeler le garage")
    return db, older, newer


def test_older_action_is_undone_from_the_home_list_and_stays_marked_undone(two_notes, page):
    db, older, newer = two_notes
    page.evaluate(f"localStorage.setItem('pah_session_id', '{SESSION}');"
                  "localStorage.setItem('pah_session_timestamp', String(Date.now()));")
    page.reload()
    page.wait_for_selector("#view-home.active")
    rows = page.locator("#home-activity-list .activity__item:has(.activity__undo)")
    rows.nth(1).wait_for()
    assert rows.count() == 2

    rows.nth(1).locator(".activity__undo").click()  # la plus ancienne des deux

    page.wait_for_selector(".notice:has-text(\"C'est annulé : note « Penser aux piles » supprimée.\")")
    page.wait_for_selector("#home-activity-list .activity__item--undone:has-text('Annulée')")
    assert db.get_note(older) is None and db.get_note(newer) is not None
    assert page.locator("#home-activity-list .activity__undo").count() == 1  # la plus récente reste annulable
