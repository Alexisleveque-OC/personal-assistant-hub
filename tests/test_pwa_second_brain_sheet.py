"""PWA : feuille « Second cerveau » (refonte UX, ROADMAP étape 7, maquette E-Notes ; décisions utilisateur du 17/11).

Puces de catégorie (Tout, Idées, À dév., Bugs, autres si non vides, Faites) ; cartes « Fait » / « En faire une tâche »
avec « Annuler » ; menu ⋯ par carte → « Supprimer » + « Annuler » (note recréée avec sa catégorie et sa date) ;
loupe = recherche ; ajout par la barre de saisie (Otis) ; « Journal & feedback » sort dans sa propre feuille.
"""
import re

from fastapi.testclient import TestClient

from app.main import app
from tests.js_helpers import rendered_html, section

client = TestClient(app)


def _static(path: str) -> str:
    return client.get(f"/static/{path}").text


def test_second_brain_sheet_has_search_chips_and_list_only():
    sheet = section(rendered_html(), "view-second-brain")
    assert re.search(r'<button type="button"[^>]*id="btn-brain-search"[^>]*aria-label="Rechercher"'
                     r'[^>]*aria-expanded="false"[^>]*aria-controls="brain-search"', sheet)
    assert re.search(r'id="brain-search"[^>]*hidden', sheet)
    assert re.search(r'<input type="search" id="brain-search-input"', sheet)
    assert re.search(r'id="brain-chips"[^>]*role="tablist"[^>]*aria-label="Catégorie"', sheet)
    assert 'id="second-brain-list"' in sheet
    assert 'class="composer-slot"' in sheet


def test_journal_and_feedback_has_its_own_sheet_opened_from_the_menu():
    html = rendered_html()
    sheet = section(html, "view-journal")
    assert '<h2 class="sheet__title" id="view-journal-title">Journal &amp; feedback</h2>' in sheet
    assert 'data-sheet-close aria-label="Fermer"' in sheet
    assert 'id="audit-logs-list"' in sheet
    assert re.search(r'id="drawer-journal"[^>]*data-section="journal"', html)
    js = (_static("app.js") + _static("js/app_shell.js"))
    assert "loadConversationAuditLogs()" in js
    assert "brainView" not in js and "getBrainSubview" not in js
