"""PWA onglet Sport : retours d'usage du 03/11 (menu allégé, séances paginées, dashboard en km, périodes passées)."""
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


def _sport_js() -> str:
    return client.get("/static/js/views/sport_view.js").text


# Étape 1 : menu allégé
def test_import_subtab_is_no_longer_rendered_but_header_import_stays():
    html = client.get("/app").text
    rendered = _without_html_comments(html)

    assert 'id="tab-sport-import"' not in rendered
    assert 'id="tab-sport-import"' in html  # bouton commenté, réactivable
    assert 'id="btn-import-sport-screenshot"' in rendered
    assert 'id="tab-sport-gamification"' in rendered and 'id="tab-sport-dash"' in rendered


# Étape 2 : séances paginées (30 par page, filtres côté serveur)
def test_sessions_are_loaded_page_by_page_with_server_filters():
    js = _sport_js()
    body = _function_body(js, "export async function fetchSportSessions(")

    assert "SESSIONS_PAGE_SIZE = 30" in js
    assert "limit: SESSIONS_PAGE_SIZE" in body
    assert "offset:" in body
    assert "statut:" in body and "type_seance:" in body
    assert "limit: 200" not in js


def test_sessions_view_shows_previous_next_and_page_counter():
    js = _sport_js()
    body = _function_body(js, "export function renderSportSessionsView(")

    assert "Précédent" in body and "Suivant" in body
    assert "Page ${" in body
    assert "sessions-page-prev" in body and "sessions-page-next" in body


def test_changing_a_filter_restarts_from_the_first_page():
    js = _sport_js()
    body = _function_body(js, "function attachSessionsFiltersHandlers(")

    assert body.count("currentSessionsPage = 0") == 2
    assert "fetchSportSessions()" in body


# Étape 3 : dashboard en km
def test_volume_card_shows_kilometres_big_and_km_effort_small():
    body = _function_body(_sport_js(), "export function renderSportDashboard(")

    assert '<div class="dash-kpi-val">${totals.distance_km || 0} <span' in body
    assert "${totals.km_effort || 0} km-effort" in body


def test_volume_chart_is_in_kilometres_without_the_ceiling_line():
    js = _sport_js()
    dash = _function_body(js, "export function renderSportDashboard(")
    metrics = js[js.index("const DASH_METRICS = {"):js.index("};", js.index("const DASH_METRICS = {"))]

    assert "renderSvgBarChart(series, metric" in dash
    assert 'volume: { title: "Évolution Volume (km)", value: (pt) => pt.distance_km' in metrics
    volume = metrics[metrics.index("volume:"):metrics.index("allure:")]
    assert "plafond" not in volume


# Graphique selon la carte cliquée (retour du 03/11)
def test_kpi_cards_select_the_chart_metric():
    js = _sport_js()
    dash = _function_body(js, "export function renderSportDashboard(")

    for metric in ("volume", "allure", "charge", "securite"):
        assert f'data-metric="{metric}"' in dash
    assert "state.currentSportMetric = " in dash
    assert "renderSportDashboard(data)" in dash  # pas de rechargement réseau au changement d'indicateur
    assert 'currentSportMetric: "volume"' in client.get("/static/js/config.js").text


def test_pace_bars_grow_with_speed_but_are_labelled_in_pace():
    js = _sport_js()
    metrics = js[js.index("const DASH_METRICS = {"):js.index("};", js.index("const DASH_METRICS = {"))]
    allure = metrics[metrics.index("allure:"):metrics.index("charge:")]

    assert "pt.vitesse_kmh" in allure
    assert "formatPace(" in allure


def test_safety_card_shows_km_effort_with_the_ceiling_line():
    js = _sport_js()
    metrics = js[js.index("const DASH_METRICS = {"):js.index("};", js.index("const DASH_METRICS = {"))]
    securite = metrics[metrics.index("securite:"):]

    assert "pt.km_effort" in securite
    assert "showCeiling: true" in securite


# Étape 4 : périodes passées
def test_dashboard_has_previous_and_next_period_arrows():
    body = _function_body(_sport_js(), "export function renderSportDashboard(")

    assert "dash-period-prev" in body and "dash-period-next" in body
    assert "data.start_date" in body and "data.end_date" in body
    assert "disabled" in body  # › grisée sur la période en cours


def test_dashboard_api_client_sends_the_reference_date():
    api = client.get("/static/js/api.js").text
    body = _function_body(api, "export async function fetchSportDashboardData(")

    assert "refDate" in body
    assert 'params.append("date", refDate)' in body


def test_switching_scale_goes_back_to_the_current_period():
    body = _function_body(_sport_js(), "export function renderSportDashboard(")

    assert "fetchSportDashboard(sc)" in body


def test_service_worker_cache_bumped_for_the_sport_tab_changes():
    assert "pah-pwa-cache-v31" in client.get("/sw.js").text
