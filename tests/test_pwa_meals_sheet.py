"""PWA : feuille « Repas » (refonte UX, ROADMAP étape 6, maquette E-Repas ; décisions utilisateur du 17/11).

Navigation ‹ › de semaine en semaine (onglet annuel « repas AAAA », retours du 17/11), bande des 7 jours (toucher un
jour fait défiler jusqu'à sa carte), les 7 jours en cartes Midi / Soir, « Ajouter » pré-remplit la barre,
« Demander une idée à Otis » sur un jour vide, ingrédients de la semaine affichée à cocher puis envoyés à Otis.
Lecture directe GET /api/v1/meals/week?offset=N : plus de question à Otis à l'ouverture.
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


def test_meals_sheet_has_a_day_strip_cards_and_the_ingredients_button():
    sheet = _section(_rendered_html(), "view-meals")
    assert 'id="meal-nav"' in sheet
    assert sheet.index('id="meal-nav"') < sheet.index('id="meal-days"')
    assert re.search(r'id="meal-days"[^>]*role="tablist"[^>]*aria-label="Jour"', sheet)
    assert 'id="meal-container"' in sheet
    assert re.search(r'<button type="button"[^>]*id="btn-meal-ingredients"[^>]*aria-expanded="false"', sheet)
    assert "Ingrédients de la semaine → courses" in sheet
    assert re.search(r'id="meal-ingredients"[^>]*hidden', sheet)
    assert "segmented-control" not in sheet and "tab-meal-today" not in sheet  # anciens onglets retirés
    assert 'class="composer-slot"' in sheet


def test_app_reloads_the_meals_sheet_from_the_week_route_only():
    js = (_static("app.js") + _static("js/app_shell.js"))
    assert "loadMeals()" in js
    assert "fetchMealToday" not in js and "currentMealSubview" not in js
    assert "currentMealSubview" not in _static("js/config.js")


def test_meals_view_reads_directly_and_renders_without_html_injection():
    view = _static("js/views/meals_view.js")
    for needle in ("fetchWeekMeals(", "fetchShoppingData(", "weekStrip(", "dayCards(", "slotPrefill(", "ideaPrompt(",
                   "weekIngredients(", "ingredientsMessage(", "sendInteraction(", "query-input", 'role", "tab"',
                   "aria-selected", "aria-expanded", "Rien de prévu", "Rien de planifié pour l'instant.",
                   "Demander une idée à Otis", "Ajouter", "déjà dans la liste", "Ajouter aux courses",
                   "periodNav(", "weekNav(", "hasIngredientsButton(", "scrollIntoView", "Semaine précédente",
                   "Semaine suivante", "Revenir à cette semaine",
                   "addOnPrefill(", "Ajouter un plat", "Supprimer", "deleteMeal(", "restoreMeal(", "Annuler",
                   "action:"):
        assert needle in view, needle
    assert "innerHTML" not in view and "postInteract" not in view and "alert(" not in view


def test_api_client_reports_the_week_route_error_detail():
    js = _static("js/api.js")
    start = js.index("export async function fetchWeekMeals(")
    body = js[start:js.index("\n}\n", start)]
    assert "detail" in body and "getAuthHeaders()" in body
    assert "export async function fetchWeekMeals(offset = 0)" in js and "offset=${" in body


def test_new_module_is_precached_and_versions_bumped():
    sw = client.get("/sw.js").text
    assert '"/static/js/meals_model.js"' in sw
    assert '"/static/js/views/meals_view.js"' in sw
    assert "pah-pwa-cache-v47" in sw
    assert "/static/app.js?v=31.0" in _rendered_html()


def test_styles_cover_the_day_strip_and_meal_rows():
    css = _static("styles/app.css")
    for selector in (".meal-head", ".meal-card", ".meal-days", ".meal-day", ".meal-day--today", ".meal-day--future", ".meal-row", ".meal-empty",
                     ".meal-ingredients", ".meal-row__panel", ".meal-row__actions"):
        assert selector in css, selector


def test_api_client_deletes_and_restores_a_meal_directly():
    """Retours du 17/11 : « Supprimer » écrit tout de suite (sans Otis), « Annuler » remet le plat."""
    js = _static("js/api.js")
    for function_name in ("deleteMeal", "restoreMeal"):
        assert f"export async function {function_name}(" in js
    assert "/api/v1/meals/plan/" in js
    assert 'method: "DELETE"' in js and 'method: "PUT"' in js
