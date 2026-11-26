"""Client HTTP de la PWA (api.js) exécuté sous Node avec fetch et FormData simulés.

Chaque appel est enregistré (url, méthode, en-têtes, corps) ; `respond(status, body, headers)` fixe la réponse suivante.
"""
import re

from tests.js_helpers import STATIC, js_source, run_node, static_source

PRELUDE = """
const state = { apiKey: "k", uiContext: "sport", uiSessionId: 7 };
const getActiveSessionId = () => "sess-1";
const calls = [];
let reply = { status: 200, body: {} };
const respond = (status, body, headers = {}) => { reply = { status, body, headers }; };
class FakeFormData {
  constructor() { this.entries = []; }
  append(key, value, filename) {
    this.entries.push([key, value && typeof value === "object" ? { type: value.type, filename: filename ?? null } : value]);
  }
}
globalThis.FormData = FakeFormData;
globalThis.fetch = async (url, init = {}) => {
  const body = init.body instanceof FakeFormData ? init.body.entries : init.body ? JSON.parse(init.body) : null;
  calls.push({ url, method: init.method || "GET", headers: init.headers || {}, body, signal: !!init.signal });
  const { status, body: payload, headers } = reply;
  return {
    ok: status < 400, status,
    headers: { get: (name) => headers[name] ?? null },
    json: async () => { if (payload === undefined) throw new Error("pas de corps"); return payload; },
  };
};
const errorOf = async (promise) => {
  try { await promise; return null; } catch (e) { return { message: e.message, status: e.status ?? null, code: e.code ?? null }; }
};
const last = () => calls[calls.length - 1];
const print = (value) => console.log(JSON.stringify(value));
"""


API_MODULES = ("http", "interact", "sport", "meals", "second_brain", "tasks", "budget")


def _run(snippet: str):
    modules = js_source(*(f"api/{name}.js" for name in API_MODULES), strip_imports=True)
    return run_node(PRELUDE + modules + "\n" + snippet)


def test_api_js_only_reexports_the_domain_modules_and_covers_every_import():
    assert static_source("js/api.js").split() == [
        token for name in API_MODULES for token in ("export", "*", "from", f'"./api/{name}.js";')
    ]
    exported = set(re.findall(r"^export (?:async )?(?:function|const) (\w+)", js_source(
        *(f"api/{name}.js" for name in API_MODULES)), re.M))
    imported = set()
    for path in [STATIC / "app.js", *(STATIC / "js").rglob("*.js")]:
        for names in re.findall(r'import\s*\{([^}]*)\}\s*from\s*"[./]*/api\.js"', path.read_text(encoding="utf-8")):
            imported |= {name.split(" as ")[0].strip() for name in names.split(",") if name.strip()}
    assert imported and imported - exported == set()


def test_interact_sends_the_open_sheet_and_the_open_session():
    out = _run("""
await postInteract("salut");
const first = last();
state.uiSessionId = undefined;
await postInteract("encore", "autre");
print([first, last()]);
""")

    first, second = out
    assert first["url"] == "/api/v1/interact" and first["method"] == "POST"
    assert first["headers"]["X-API-Key"] == "k"
    assert first["body"] == {"query": "salut", "session_id": "sess-1", "context": {"ui_context": "sport", "ui_session_id": 7}}
    assert second["body"]["session_id"] == "autre" and second["body"]["context"]["ui_session_id"] is None


def test_interact_can_add_flags_to_the_context():
    out = _run("""
await postInteract("Approfondis", null, { expert_detailed: true });
print(last().body);
""")

    assert out == {"query": "Approfondis", "session_id": "sess-1",
                   "context": {"ui_context": "sport", "ui_session_id": 7, "expert_detailed": True}}


def test_audio_is_named_after_its_mime_type_and_the_request_can_be_aborted():
    out = _run("""
const names = [];
for (const type of ["audio/mp4", "audio/ogg;codecs=opus", "audio/wav", "audio/webm", ""]) {
  await postInteractAudio({ type });
  names.push(last().body[0][1].filename);
}
print({ names, call: last() });
""")

    assert out["names"] == ["recording.mp4", "recording.ogg", "recording.wav", "recording.webm", "recording.webm"]
    call = out["call"]
    assert call["url"] == "/api/v1/interact/audio" and call["signal"] is True
    assert call["headers"] == {"X-API-Key": "k"}  # multipart : pas de Content-Type, le navigateur pose la frontière
    assert [key for key, _ in call["body"]] == ["audio_file", "session_id", "context"]


def test_sport_draft_dashboard_and_screenshot_import():
    out = _run("""
await postSportSessionDraft({ type: "audio/ogg" });
const draft = last();
await fetchSportDashboardData("month", "2026-10-01");
const withDate = last().url;
await fetchSportDashboardData();
const current = last().url;
respond(400, { detail: "Date absente" }, { "X-Error-Code": "DATE_MISSING" });
const importError = await errorOf(importSportScreenshot({ type: "image/png" }, { referenceDate: "2026-11-18" }));
print({ draft, withDate, current, importUrl: last().url, importError });
""")

    assert out["draft"]["url"] == "/api/v1/sport/session/draft"
    assert out["draft"]["body"] == [["audio_file", {"type": "audio/ogg", "filename": "dictee.ogg"}]]
    assert "Content-Type" not in out["draft"]["headers"]
    assert out["withDate"] == "/api/v1/sport/dashboard?scale=month&date=2026-10-01"
    assert out["current"] == "/api/v1/sport/dashboard?scale=week"
    assert out["importUrl"] == "/api/v1/sport/import-screenshot?reference_date=2026-11-18"
    assert out["importError"] == {"message": "Date absente", "status": 400, "code": "DATE_MISSING"}


def test_tasks_read_toggle_reopen_with_the_hour_and_delete_without_body():
    out = _run("""
await fetchTasks();
const list = last();
await setTaskCompleted("a b", false, { heure: "09:00", rappel_minutes_avant: 10 });
const reopen = last();
await setTaskCompleted("a b", true, { heure: "09:00", rappel_minutes_avant: 10 });
const done = last().body;
respond(204, undefined);
const deleted = await deleteTask("x/1");
const deleteCall = last();
respond(503, { detail: "Google Tasks non configuré" });
const detailError = await errorOf(fetchTasks());
respond(500, { detail: [{ msg: "objet" }] });
const fallbackError = await errorOf(createTask("Pain"));
print({ list, reopen, done, deleted, deleteCall, detailError, fallbackError });
""")

    assert out["list"]["url"] == "/api/v1/tasks" and out["list"]["method"] == "GET"
    assert out["reopen"]["url"] == "/api/v1/tasks/a%20b" and out["reopen"]["method"] == "PATCH"
    assert out["reopen"]["body"] == {"terminee": False, "heure": "09:00", "rappel_minutes_avant": 10}
    assert out["done"] == {"terminee": True}
    assert out["deleted"] is None
    assert out["deleteCall"]["url"] == "/api/v1/tasks/x%2F1" and out["deleteCall"]["method"] == "DELETE"
    assert out["detailError"]["message"] == "Google Tasks non configuré"
    assert out["fallbackError"]["message"] == "Échec de l'ajout de la tâche (500)"


def test_meals_week_offset_delete_restore_and_error_detail():
    out = _run("""
await fetchWeekMeals(-1);
const week = last().url;
await deleteMeal("2026-11-18", "soir");
const deleted = last();
await restoreMeal("2026-11-18", "soir", "Gratin");
const restored = last();
respond(404, { detail: "Onglet « repas 2026 » introuvable" });
const weekError = await errorOf(fetchWeekMeals());
print({ week, deleted, restored, weekError });
""")

    assert out["week"] == "/api/v1/meals/week?offset=-1"
    assert out["deleted"]["url"] == "/api/v1/meals/plan/2026-11-18/soir" and out["deleted"]["method"] == "DELETE"
    assert out["restored"]["method"] == "PUT" and out["restored"]["body"] == {"plat": "Gratin"}
    assert out["restored"]["headers"]["Content-Type"] == "application/json"
    assert out["weekError"]["message"] == "Onglet « repas 2026 » introuvable"


def test_second_brain_notes_report_the_server_detail_or_a_fallback():
    out = _run("""
respond(422, { detail: "Contenu vide" });
const detail = await errorOf(createSecondBrainNote({ content: "" }));
respond(500, { detail: [{ msg: "objet" }] });
const fallback = await errorOf(patchSecondBrainNote(3, { content: "x" }));
const patchCall = last();
respond(500, undefined);
const noBody = await errorOf(deleteSecondBrainNote(3));
print({ detail, fallback, patchCall, noBody, deleteCall: last() });
""")

    assert out["detail"]["message"] == "Contenu vide"
    assert out["fallback"]["message"] == "Note non mise à jour (500)"
    assert out["patchCall"]["url"] == "/api/v1/second-brain/notes/3" and out["patchCall"]["method"] == "PATCH"
    assert out["noBody"]["message"] == "Note non supprimée (500)"
    assert out["deleteCall"]["method"] == "DELETE"


def test_a_recent_action_is_undone_by_its_direct_route_with_the_device_session():
    out = _run("""
respond(200, { spoken_response: "C'est annulé : note supprimée." });
const ok = await undoRecentAction(12, "pwa 1");
const call = last();
respond(409, { detail: "Annulation impossible : Lait a été coché depuis." });
const refused = await errorOf(undoRecentAction(13, "pwa 1"));
print({ ok, call, refused });
""")

    assert out["ok"] == {"spoken_response": "C'est annulé : note supprimée."}
    assert out["call"]["url"] == "/api/v1/home/recent-actions/12/undo?session_id=pwa+1"
    assert out["call"]["method"] == "POST" and out["call"]["headers"]["X-API-Key"] == "k"
    assert out["refused"]["message"] == "Annulation impossible : Lait a été coché depuis."


def test_budget_entry_is_posted_as_json_and_reports_the_server_detail():
    out = _run("""
respond(201, { message: "Dépense enregistrée : 12,5 € en Course", action_id: 4 });
const ok = await addBudgetEntry({ type: "depense", montant: 12.5 });
const call = last();
respond(422, { detail: "Catégorie « Jardin » inconnue du budget." });
const refused = await errorOf(addBudgetEntry({}));
respond(422, { detail: [{ msg: "objet" }] });
const fallback = await errorOf(addBudgetEntry({}));
print({ ok, call, refused, fallback });
""")

    assert out["ok"]["action_id"] == 4
    assert out["call"]["url"] == "/api/v1/budget/entries" and out["call"]["method"] == "POST"
    assert out["call"]["headers"]["Content-Type"] == "application/json"
    assert out["call"]["body"] == {"type": "depense", "montant": 12.5}
    assert out["refused"]["message"] == "Catégorie « Jardin » inconnue du budget."
    assert out["fallback"]["message"] == "Saisie non enregistrée (422)"
