"""PWA : feuille « Second cerveau » (refonte UX, ROADMAP étape 7, maquette E-Notes ; décisions utilisateur du 17/11).

Puces de catégorie (Tout, Idées, À dév., Bugs, autres si non vides, Faites) ; cartes « Fait » / « En faire une tâche »
avec « Annuler » ; menu ⋯ par carte → « Supprimer » + « Annuler » (note recréée avec sa catégorie et sa date) ;
loupe = recherche ; ajout par la barre de saisie (Otis) ; « Journal & feedback » sort dans sa propre feuille.
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


def test_second_brain_sheet_has_search_chips_and_list_only():
    sheet = _section(_rendered_html(), "view-second-brain")
    assert re.search(r'<button type="button"[^>]*id="btn-brain-search"[^>]*aria-label="Rechercher"'
                     r'[^>]*aria-expanded="false"[^>]*aria-controls="brain-search"', sheet)
    assert re.search(r'id="brain-search"[^>]*hidden', sheet)
    assert re.search(r'<input type="search" id="brain-search-input"', sheet)
    assert re.search(r'id="brain-chips"[^>]*role="tablist"[^>]*aria-label="Catégorie"', sheet)
    assert 'id="second-brain-list"' in sheet
    assert 'class="composer-slot"' in sheet
    for removed in ("segmented-control", "form-add-note", "brain-status-filter", "btn-add-note-inline",
                    "btn-upload-image-inline", "tab-brain-audit", "audit-logs-list", "brain-image-status-banner"):
        assert removed not in sheet, removed


def test_journal_and_feedback_has_its_own_sheet_opened_from_the_menu():
    html = _rendered_html()
    sheet = _section(html, "view-journal")
    assert '<h2 class="sheet__title" id="view-journal-title">Journal &amp; feedback</h2>' in sheet
    assert 'data-sheet-close aria-label="Fermer"' in sheet
    assert 'id="audit-logs-list"' in sheet
    assert re.search(r'id="drawer-journal"[^>]*data-section="journal"', html)
    js = (_static("app.js") + _static("js/app_shell.js"))
    assert "loadConversationAuditLogs()" in js
    assert "brainView" not in js and "getBrainSubview" not in js


def test_journal_section_and_view_module():
    shell = _static("js/ui_shell.js")
    assert 'journal: { sheetId: "view-journal"' in shell
    journal = _static("js/views/journal_view.js")
    assert "export async function loadConversationAuditLogs(" in journal and "postConversationFeedback(" in journal
    assert "loadConversationAuditLogs" not in _static("js/views/second_brain_view.js")


def test_second_brain_view_uses_the_model_and_renders_without_html_injection():
    view = _static("js/views/second_brain_view.js")
    for needle in ("noteChips(", "noteCard(", "notesQuery(", "restorePayload(", "taskTitle(", "emptyText(",
                   "fetchSecondBrainNotes(", "fetchSecondBrainStats(", "patchSecondBrainNote(",
                   "deleteSecondBrainNote(", "createSecondBrainNote(", "createTask(", "deleteTask(",
                   "Fait", "En faire une tâche", "Rouvrir", "Supprimer", "Annuler", "Plus d'options",
                   'role", "menu"', "menuitem", "menu-pop", "aria-expanded", "aria-selected", "action:",
                   "second-brain-updated"):
        assert needle in view, needle
    for forbidden in ("innerHTML", "alert(", "confirm(", "switchBrainSubview"):
        assert forbidden not in view, forbidden


def test_brain_image_from_the_composer_refreshes_the_sheet():
    assert 'new CustomEvent("second-brain-updated")' in _static("js/views/chat_view.js")


def test_api_client_deletes_a_task_and_reports_note_errors_in_detail():
    js = _static("js/api.js")
    start = js.index("export async function deleteTask(")
    body = js[start:js.index("\n}\n", start)]
    assert 'method: "DELETE"' in body and "/api/v1/tasks/" in body
    assert "res.status === 204" in js  # suppression sans corps de réponse
    for function_name in ("createSecondBrainNote", "patchSecondBrainNote", "deleteSecondBrainNote"):
        start = js.index(f"export async function {function_name}(")
        assert "brainRequest(" in js[start:js.index("\n}\n", start)], function_name
    start = js.index("async function brainRequest(")
    assert "detail" in js[start:js.index("\n}\n", start)]


def test_new_modules_are_precached_and_versions_bumped():
    sw = client.get("/sw.js").text
    assert '"/static/js/notes_model.js"' in sw
    assert '"/static/js/views/journal_view.js"' in sw
    assert "pah-pwa-cache-v48" in sw
    assert "/static/app.js?v=31.0" in _rendered_html()


def test_styles_cover_chips_cards_and_search():
    css = _static("styles/app.css")
    for selector in (".chips--scroll", ".brain-search", ".note-card", ".note-card__head", ".note-card__actions",
                     ".note-card__label--idea", ".note-card__label--dev", ".note-card__label--bug",
                     ".note-card__label--pref", ".note-card__label--task", ".note-card__label--other",
                     ".note-card__done"):
        assert selector in css, selector
