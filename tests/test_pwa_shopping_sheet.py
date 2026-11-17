"""Refonte UX (ROADMAP Étape 4) : feuille Courses (maquette E-Courses)."""
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
client = TestClient(app)


def _rendered_html() -> str:
    return re.sub(r"<!--.*?-->", "", client.get("/app").text, flags=re.DOTALL)


def _section(html: str, sheet_id: str) -> str:
    start = html.index(f'id="{sheet_id}"')
    return html[start:html.index("</section>", start)]


def _static(path: str) -> str:
    return (STATIC / path).read_text(encoding="utf-8")


def test_header_has_a_more_options_menu_with_reset_and_clear():
    sheet = _section(_rendered_html(), "view-shopping")

    assert ">Courses</h2>" in sheet
    more = sheet.split('id="btn-shopping-more"')[1][:200]
    assert 'aria-label="Plus d\'options"' in more and 'aria-haspopup="menu"' in more and 'aria-expanded="false"' in more
    menu = sheet.split('id="shopping-menu"')[1].split("</div>")[0]
    assert 'role="menu"' in menu and "hidden" in menu
    assert 'id="btn-reset-shopping" role="menuitem"' in menu and "Réinitialiser la semaine" in menu
    assert 'id="btn-clear-bought" role="menuitem"' in menu and "Vider les achetés" in menu
    assert 'data-sheet-close aria-label="Fermer"' in sheet


def test_two_pill_tabs_with_remaining_counts():
    sheet = _section(_rendered_html(), "view-shopping")

    assert 'class="seg" role="tablist" aria-label="Liste"' in sheet
    assert 'role="tab" id="tab-cette-semaine" aria-selected="true"' in sheet
    assert 'role="tab" id="tab-liste-attente" aria-selected="false"' in sheet
    assert 'id="badge-cette-semaine"' in sheet and 'id="badge-liste-attente"' in sheet
    assert ">En attente" in sheet


def test_list_banner_and_composer_slot_but_no_legacy_controls():
    sheet = _section(_rendered_html(), "view-shopping")

    assert 'id="shopping-list-container"' in sheet
    assert 'id="shopping-completion-banner"' in sheet
    assert "composer-slot" in sheet
    for legacy in ("segmented-control", "seg-btn", "btn-check-completion", "shopping-header", "btn-action-small"):
        assert legacy not in sheet, legacy


def test_view_reads_the_direct_route_and_never_asks_otis():
    view = _static("js/views/shopping_view.js")

    assert "fetchShoppingData" in view
    assert "Donne-moi la liste de courses" not in view
    # Seule écriture confiée à Otis : « Vider les achetés » (journalisée, donc annulable depuis l'accueil)
    assert view.count("postInteract(") == 1 and 'postInteract("Vide la liste de courses")' in view


def test_view_uses_the_hub_list_classes_and_the_model():
    view = _static("js/views/shopping_view.js")

    for needle in ("list-group", "list-group__head", "list-row", "list-row__text", "list-row__qty", '"check"',
                   "btn btn--primary btn--block", "J'ai fini mes courses", "callout", "groupByRayon", "shoppingLists",
                   "remainingCount", "completionMessage", "toggleStoredCheck", "showToast"):
        assert needle in view, needle
    assert "innerHTML" not in view and "alert(" not in view


def test_new_module_is_precached_and_shell_version_bumped():
    sw = _static("sw.js")
    assert '"/static/js/shopping_model.js"' in sw
    assert "pah-pwa-cache-v43" in sw
    assert "/static/app.js?v=28.0" in _rendered_html()
