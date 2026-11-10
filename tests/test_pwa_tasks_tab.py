"""PWA : onglet « Tâches » (Phase 8, étape 4 bis, décisions utilisateur du 03/11).

6e bouton de la barre du bas ; cocher écrit tout de suite dans Google Tasks et propose « Annuler » (tâche rouverte).
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_menu_has_a_tasks_entry_and_a_tasks_sheet():
    html = client.get("/app").text

    assert 'data-section="taches"' in html
    assert 'id="view-tasks"' in html
    assert 'id="tasks-list-container"' in html
    assert 'id="tasks-add-form"' in html


def test_app_wires_the_tasks_view_and_reloads_it_when_the_sheet_opens():
    js = client.get("/static/app.js").text
    shell = client.get("/static/js/ui_shell.js").text

    assert 'from "./js/views/tasks_view.js"' in js
    assert "initTasksView()" in js
    assert 'sheetId: "view-tasks"' in shell
    assert 'section === "taches"' in js and "loadTasks()" in js


def test_api_client_reads_adds_and_toggles_tasks():
    js = client.get("/static/js/api.js").text

    for function_name in ("fetchTasks", "createTask", "setTaskCompleted"):
        assert f"export async function {function_name}(" in js
    assert '"/api/v1/tasks"' in js
    assert 'method: "PATCH"' in js


def test_checking_a_task_writes_immediately_and_offers_undo():
    js = client.get("/static/js/views/tasks_view.js").text

    assert "setTaskCompleted(" in js
    assert "Annuler" in js
    assert "action:" in js  # toast avec bouton d'action


def test_toast_supports_an_action_button():
    js = client.get("/static/js/toast.js").text

    assert "action" in js
    assert "btn-undo-action" in js


def test_service_worker_caches_the_tasks_view_with_a_new_version():
    sw = client.get("/sw.js").text

    assert "/static/js/views/tasks_view.js" in sw
    assert "/static/js/toast.js" in sw
    assert "pah-pwa-cache-v33" in sw
