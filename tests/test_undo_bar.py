"""Barre « Annuler » de la conversation (undo_bar.js) exécutée sous Node avec un faux DOM."""
from tests.js_helpers import js_source, run_node

FAKES = """
const elements = { "undo-toast": { hidden: true }, "undo-toast-text": { textContent: "" }, "btn-undo-action": {} };
globalThis.document = { getElementById: (id) => elements[id] || null };
const timers = new Map();
let timerId = 0;
globalThis.setTimeout = (fn, ms) => { timers.set(++timerId, { fn, ms }); return timerId; };
globalThis.clearTimeout = (id) => timers.delete(id);
const print = (value) => console.log(JSON.stringify(value));
"""


def _run(snippet: str):
    return run_node(FAKES + js_source("undo_bar.js") + "\n" + snippet)


def test_undo_bar_shows_the_action_and_undoes_it_once_clicked():
    out = _run("""
let undone = 0;
showUndoToast("Lait ajouté aux courses", () => { undone += 1; });
const shown = { hidden: elements["undo-toast"].hidden, text: elements["undo-toast-text"].textContent };
elements["btn-undo-action"].onclick();
print({ shown, hiddenAfterClick: elements["undo-toast"].hidden, undone, pending: timers.size });
""")

    assert out == {"shown": {"hidden": False, "text": "Lait ajouté aux courses"}, "hiddenAfterClick": True,
                   "undone": 1, "pending": 0}


def test_undo_bar_hides_itself_after_8_seconds_and_a_new_action_restarts_the_delay():
    out = _run("""
showUndoToast("", () => {});
showUndoToast("Deuxième", () => {});
const delays = [...timers.values()].map((t) => t.ms);
[...timers.values()][0].fn();
print({ delays, text: elements["undo-toast-text"].textContent, hidden: elements["undo-toast"].hidden });
""")

    assert out == {"delays": [8000], "text": "Deuxième", "hidden": True}
