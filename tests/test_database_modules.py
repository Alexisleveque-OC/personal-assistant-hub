"""Refacto anti-tokens, lot 3 : database.py devient un paquet, un module par domaine,
assemblés dans DatabaseManager sans changer l'interface vue par les appelants."""
import sqlite3
from pathlib import Path

from app.core.database import DatabaseManager, get_database_manager, set_database_manager
from app.core.database.conversation import ConversationStore
from app.core.database.learnings import LearningsStore
from app.core.database.notes import NotesStore
from app.core.database.sport import SportStore

PACKAGE = Path(__file__).resolve().parent.parent / "app" / "core" / "database"

PUBLIC_METHODS = {
    "get_connection", "init_db",
    "add_agent_undo_batch", "get_last_agent_undo_batch", "mark_agent_undo_batch_undone",
    "log_conversation", "get_conversation_log", "get_conversation_logs", "add_feedback", "get_feedbacks_for_log",
    "add_note", "get_note", "get_notes", "update_note", "delete_note", "get_notes_stats",
    "add_learning", "get_learning", "get_learnings", "get_active_learnings", "update_learning", "delete_learning",
    "add_sport_session", "get_sport_session_by_id", "get_sport_session_by_date", "get_sport_sessions",
    "get_last_sport_session", "update_sport_session", "delete_sport_session", "upsert_sport_weekly_summary",
    "get_sport_weekly_summary", "get_all_sport_weekly_summaries", "delete_sport_weekly_summary",
}


def test_database_is_a_package_with_one_module_per_domain():
    for module in ("__init__", "base", "conversation", "notes", "learnings", "sport"):
        source = PACKAGE / f"{module}.py"
        assert source.exists(), module
        assert len(source.read_text(encoding="utf-8").splitlines()) < 400, f"{module}.py trop long"


def test_manager_assembles_the_domain_stores_with_the_same_public_interface():
    for store in (ConversationStore, NotesStore, LearningsStore, SportStore):
        assert issubclass(DatabaseManager, store)
    public = {name for name in dir(DatabaseManager) if not name.startswith("_")}
    assert public == PUBLIC_METHODS


def test_init_db_still_creates_every_table(tmp_path):
    db = DatabaseManager(str(tmp_path / "hub.db"))
    db.init_db()
    with sqlite3.connect(db.db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {
        "conversation_logs", "conversation_feedbacks", "user_learnings", "second_brain_notes",
        "sport_sessions", "sport_weekly_summaries", "agent_undo_batches",
    } <= tables


def test_singleton_accessors_are_unchanged(tmp_path):
    manager = DatabaseManager(str(tmp_path / "other.db"))
    set_database_manager(manager)
    try:
        assert get_database_manager() is manager
    finally:
        set_database_manager(None)
