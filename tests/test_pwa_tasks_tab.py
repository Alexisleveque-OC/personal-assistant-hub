"""PWA : feuille « Tâches » (refonte UX, ROADMAP étape 5, maquette E-Taches ; décisions utilisateur du 16/11).

Sections En retard / Cette semaine / Plus tard / Sans date, groupes = sous-tâches Google, bouton ↗ (1re URL),
cocher écrit tout de suite dans Google Tasks et propose « Annuler » (la tâche et son heure sont rétablies).
Ajout par la barre de saisie (Otis) ; le bouton calendrier joint la date et l'heure facultative au message.
"""
import re

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _rendered_html() -> str:
    return re.sub(r"<!--.*?-->", "", client.get("/app").text, flags=re.DOTALL)


def _section(html: str, sheet_id: str) -> str:
    start = html.index(f'id="{sheet_id}"')
    return html[start:html.index("</section>", start)]


def _static(path: str) -> str:
    return client.get(f"/static/{path}").text


def test_menu_has_a_tasks_entry_and_a_tasks_sheet_with_count_and_list():
    html = _rendered_html()
    sheet = _section(html, "view-tasks")
    assert 'data-section="taches"' in html
    assert 'id="tasks-count"' in sheet
    assert 'id="tasks-list-container"' in sheet
    assert "tasks-add-form" not in sheet  # l'ajout passe par la barre de saisie (maquette)
    assert 'class="composer-slot"' in sheet


def test_composer_has_a_due_picker_hidden_outside_tasks():
    html = _rendered_html()
    composer = html[html.index('id="query-form"'):html.index("</form>", html.index('id="query-form"'))]
    assert re.search(r'id="btn-composer-due"[^>]*aria-label="Choisir une date"[^>]*hidden', composer)
    assert 'id="composer-due-label"' in composer
    pop = html[html.index('id="composer-due-pop"'):]
    assert 'type="date" id="composer-due-date"' in pop
    assert 'type="time" id="composer-due-time"' in pop
    assert 'id="btn-composer-due-ok"' in pop and 'id="btn-composer-due-clear"' in pop


def test_app_wires_the_tasks_view_and_reloads_it_when_the_sheet_opens():
    js = _static("app.js")
    shell = _static("js/ui_shell.js")
    assert 'from "./js/views/tasks_view.js"' in js
    assert "initTasksView()" in js
    assert 'sheetId: "view-tasks"' in shell
    assert 'section === "taches"' in js and "loadTasks()" in js
    assert "setDuePickerVisible(" in js  # calendrier de la barre : feuille Tâches seulement


def test_api_client_reads_and_toggles_tasks_and_reopens_with_the_hour():
    js = _static("js/api.js")
    for function_name in ("fetchTasks", "createTask", "setTaskCompleted"):
        assert f"export async function {function_name}(" in js
    assert '"/api/v1/tasks"' in js
    assert 'method: "PATCH"' in js
    assert "rappel_minutes_avant" in js and "heure" in js


def test_view_renders_the_model_without_html_injection():
    view = _static("js/views/tasks_view.js")
    for needle in ("taskSheet", "list-group", "list-row", '"check"', "section-label", "badge", "setTaskCompleted(",
                   "Annuler", "action:", 'target = "_blank"', "noopener", "Ouvrir le lien"):
        assert needle in view, needle
    assert "innerHTML" not in view and "alert(" not in view


def test_text_sent_from_the_tasks_sheet_carries_the_chosen_due_date():
    chat = _static("js/views/chat_view.js")
    assert "withDue(" in chat
    assert "clearComposerDue(" in chat


def test_home_counts_rows_not_group_parents():
    home = _static("js/views/home_view.js")
    assert "openRows(" in home


def test_toast_supports_an_action_button():
    js = _static("js/toast.js")
    assert "action" in js
    assert "btn-undo-action" in js


def test_new_modules_are_precached_and_versions_bumped():
    sw = client.get("/sw.js").text
    for path in ("/static/js/views/tasks_view.js", "/static/js/tasks_model.js", "/static/js/views/task_due_picker.js",
                 "/static/js/toast.js"):
        assert f'"{path}"' in sw, path
    assert "pah-pwa-cache-v43" in sw
    assert "/static/app.js?v=28.0" in _rendered_html()
