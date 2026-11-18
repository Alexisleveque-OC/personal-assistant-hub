"""PWA Sport : retours d'usage du 03/11 conservés dans la refonte (capture de montre, séances paginées avec
filtres serveur, graphique en km selon la tuile touchée, périodes passées)."""
import re

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _without_html_comments(html: str) -> str:
    return re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)


def _function_body(js: str, signature: str) -> str:
    start = js.index(signature)
    following = js.find("\nexport ", start + 1)
    following_private = js.find("\nfunction ", start + 1)
    ends = [i for i in (following, following_private) if i != -1]
    return js[start:min(ends) if ends else len(js)]


def _js(path: str) -> str:
    return client.get(f"/static/js/{path}").text


# Étape 1 : import par capture depuis la barre d'actions (plus de sous-onglet)
def test_screenshot_import_stays_reachable_from_the_action_bar():
    rendered = _without_html_comments(client.get("/app").text)

    assert 'id="tab-sport-import"' not in rendered
    assert 'id="btn-import-sport-screenshot"' in rendered
    assert 'id="file-sport-screenshot-input"' in rendered
    assert 'getElementById("btn-import-sport-screenshot")' in _js("views/sport_view.js")


# Étape 2 : séances paginées (30 par page, filtres côté serveur)
def test_sessions_are_loaded_page_by_page_with_server_filters():
    js = _js("views/sport/sessions_list_view.js")
    body = _function_body(js, "export async function renderSessionsList(")

    assert "SESSIONS_PAGE_SIZE = 30" in js
    assert "limit: SESSIONS_PAGE_SIZE" in body
    assert "offset: filters.page * SESSIONS_PAGE_SIZE" in body
    assert "statut: filters.statut" in body and "type_seance: filters.type" in body


def test_sessions_view_shows_previous_next_and_page_counter():
    body = _function_body(_js("views/sport/sessions_list_view.js"), "function pagination(")

    assert '"Précédent"' in body and '"Suivant"' in body
    assert "`Page ${filters.page + 1} / ${pages}`" in body


def test_changing_a_filter_restarts_from_the_first_page():
    body = _function_body(_js("views/sport/sessions_list_view.js"), "function filterSelect(")

    assert "filters.page = 0" in body
    assert "renderSessionsList(container)" in body


# Étape 3 : graphique en km par défaut, indicateur choisi en touchant une tuile (sans recharger)
def test_period_tiles_select_the_chart_metric_without_reloading():
    js = _js("views/sport/period_view.js")
    tile = _function_body(js, "function metricTile(")

    assert "state.currentSportMetric = " in tile
    assert "periodBlocks(dash, container, view.milestone)" in tile  # données déjà chargées
    for metric in ('"allure"', '"effort"', '"charge"'):
        assert metric in _function_body(js, "function periodBlocks(")
    assert 'currentSportMetric: "volume"' in _js("config.js")


# Étape 4 : périodes passées
def test_week_and_period_views_have_previous_and_next_arrows():
    js = _js("views/sport/period_view.js")

    assert '"Semaine précédente"' in js and '"Semaine suivante"' in js
    assert "onNext: current ? null" in js  # › désactivée sur la période en cours
    assert "previousRef(dash)" in js and "nextRef(dash)" in js


def test_dashboard_api_client_sends_the_reference_date():
    body = _function_body(_js("api.js"), "export async function fetchSportDashboardData(")

    assert "refDate" in body
    assert 'params.append("date", refDate)' in body


def test_service_worker_cache_bumped_for_the_sport_tab_changes():
    assert "pah-pwa-cache-v48" in client.get("/sw.js").text
