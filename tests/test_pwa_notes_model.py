"""Refonte UX (ROADMAP Étape 7, maquette E-Notes) : feuille Second cerveau — logique d'affichage pure.

Le module `notes_model.js` (sans import ni DOM) est exécuté sous Node.
Décisions du 17/11 : puces Tout, Idées, À dév., Bugs toujours ; autres catégories seulement si elles ont des notes ;
puce « Faites » en fin de rangée ; « Supprimer » puis « Annuler » recrée la note avec sa catégorie et sa date.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
WINDOWS_NODE = Path("/mnt/c/Program Files/nodejs/node.exe")
NODE = shutil.which("node") or (str(WINDOWS_NODE) if WINDOWS_NODE.exists() else None)
NOW = "2026-11-17T12:00:00Z"
STATS = {"dev_idea": 1, "bug_report": 0, "thought": 2, "preference": 0, "task": 0}


def _run(snippet: str):
    if not NODE:
        pytest.skip("Node.js indisponible pour exécuter le module JS")
    source = (STATIC / "js" / "notes_model.js").read_text(encoding="utf-8") + "\n" + snippet
    result = subprocess.run([NODE, "--input-type=module"], input=source, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def chips(stats, selected="all"):
    return _run(f"console.log(JSON.stringify(noteChips({json.dumps(stats)}, {json.dumps(selected)})));")


def card(note):
    return _run(f"console.log(JSON.stringify(noteCard({json.dumps(note)}, new Date('{NOW}'))));")


def note(category="thought", status="active", created_at="2026-11-05 17:36:12", **extra):
    return {"id": 7, "category": category, "content": "Idée de cadeau pour Manon", "tags": ["cadeau"],
            "status": status, "created_at": created_at, **extra}


def test_fixed_chips_with_counts_and_done_chip_at_the_end():
    out = chips(STATS)
    assert [(c["key"], c["text"], c["selected"]) for c in out] == [
        ("all", "Tout · 3", True),
        ("thought", "Idées · 2", False),
        ("dev_idea", "À dév. · 1", False),
        ("bug_report", "Bugs", False),
        ("done", "Faites", False),
    ]


def test_other_categories_only_when_they_have_notes_known_ones_first_then_free_ones_by_name():
    out = chips({**STATS, "task": 2, "voyage": 1, "cuisine": 3, "jardin_potager": 1, "preference": 0})
    assert [c["text"] for c in out] == [
        "Tout · 10", "Idées · 2", "À dév. · 1", "Bugs", "Tâches · 2", "Cuisine · 3", "Jardin potager · 1",
        "Voyages · 1", "Faites",
    ]


def test_selected_category_stays_visible_once_emptied():
    out = chips(STATS, "voyage")
    assert [(c["key"], c["text"], c["selected"]) for c in out][-2:] == [
        ("voyage", "Voyages", True), ("done", "Faites", False),
    ]
    assert out[0]["selected"] is False


def test_query_of_each_chip():
    out = _run("console.log(JSON.stringify(['all', 'done', 'thought'].map(notesQuery)));")
    assert out == [
        {"category": None, "status": "active"},
        {"category": None, "status": "done"},
        {"category": "thought", "status": "active"},
    ]


def test_card_label_tone_and_paris_date_from_the_utc_database_date():
    out = card(note())
    assert (out["id"], out["label"], out["tone"], out["date"], out["text"]) == (
        7, "Idée", "idea", "5 nov. · 18:36", "Idée de cadeau pour Manon",
    )
    assert (out["done"], out["actions"]) == (False, ["done", "task"])


def test_card_date_in_summer_time_and_previous_year():
    assert card(note(created_at="2026-07-05 16:00:00"))["date"] == "5 juil. · 18:00"
    assert card(note(created_at="2025-12-31 23:30:00"))["date"] == "1 janv. · 00:30"
    assert card(note(created_at="2025-12-30 10:00:00"))["date"] == "30 déc. 2025 · 11:00"
    assert card(note(created_at=None))["date"] == ""


def test_card_labels_of_each_category_and_done_notes_can_only_be_reopened():
    labels = {c: (card(note(category=c))["label"], card(note(category=c))["tone"])
              for c in ("dev_idea", "bug_report", "preference", "task", "voyage", "jardin_potager")}
    assert labels == {
        "dev_idea": ("À développer", "dev"), "bug_report": ("Bug", "bug"), "preference": ("Préférence", "pref"),
        "task": ("Tâche", "task"), "voyage": ("Voyage", "other"), "jardin_potager": ("Jardin potager", "other"),
    }
    done = card(note(status="done"))
    assert (done["done"], done["actions"]) == (True, ["reopen"])


def test_restore_payload_keeps_category_text_tags_and_date():
    out = _run(f"console.log(JSON.stringify(restorePayload({json.dumps(note(category='voyage'))})));")
    assert out == {"category": "voyage", "content": "Idée de cadeau pour Manon", "tags": ["cadeau"],
                   "created_at": "2026-11-05 17:36:12"}


def test_empty_messages():
    out = _run("console.log(JSON.stringify([emptyText('all', ''), emptyText('done', ''), emptyText('bug_report', ''), "
               "emptyText('all', 'vélo')]));")
    assert out == [
        "Aucune note. Dites « Otis, note que… » ou écrivez ci-dessous.",
        "Aucune note faite.",
        "Aucune note dans « Bugs ».",
        "Aucune note ne contient « vélo ».",
    ]


def test_task_title_is_the_note_text_trimmed():
    out = _run("console.log(JSON.stringify(taskTitle({ content: '  Appeler le garage \\n ' })));")
    assert out == "Appeler le garage"
