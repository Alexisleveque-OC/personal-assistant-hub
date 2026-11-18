"""PWA : feuille « Tâches » (refonte UX, ROADMAP étape 5, maquette E-Taches ; décisions utilisateur du 16/11).

Sections En retard / Cette semaine / Plus tard / Sans date, groupes = sous-tâches Google, bouton ↗ (1re URL),
cocher écrit tout de suite dans Google Tasks et propose « Annuler » (la tâche et son heure sont rétablies).
Ajout par la barre de saisie (Otis) ; le bouton calendrier joint la date et l'heure facultative au message.
"""
import re

from fastapi.testclient import TestClient

from app.main import app
from tests.js_helpers import rendered_html, section

client = TestClient(app)


def _static(path: str) -> str:
    return client.get(f"/static/{path}").text


def test_menu_has_a_tasks_entry_and_a_tasks_sheet_with_count_and_list():
    html = rendered_html()
    sheet = section(html, "view-tasks")
    assert 'data-section="taches"' in html
    assert 'id="tasks-count"' in sheet
    assert 'id="tasks-list-container"' in sheet
    assert "tasks-add-form" not in sheet  # l'ajout passe par la barre de saisie (maquette)
    assert 'class="composer-slot"' in sheet


def test_composer_has_a_due_picker_hidden_outside_tasks():
    html = rendered_html()
    composer = html[html.index('id="query-form"'):html.index("</form>", html.index('id="query-form"'))]
    assert re.search(r'id="btn-composer-due"[^>]*aria-label="Choisir une date"[^>]*hidden', composer)
    assert 'id="composer-due-label"' in composer
    pop = html[html.index('id="composer-due-pop"'):]
    assert 'type="date" id="composer-due-date"' in pop
    assert 'type="time" id="composer-due-time"' in pop
    assert 'id="btn-composer-due-ok"' in pop and 'id="btn-composer-due-clear"' in pop


def test_view_renders_the_model_without_html_injection():
    view = _static("js/views/tasks_view.js")
    for needle in ("taskSheet", "list-group", "list-row", '"check"', "section-label", "badge", "setTaskCompleted(",
                   "Annuler", "action:", 'target = "_blank"', "noopener", "Ouvrir le lien"):
        assert needle in view, needle
    assert "innerHTML" not in view and "alert(" not in view
