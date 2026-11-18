"""Test E2E de la navigation de la PWA (refonte UX, étape 8) dans un vrai Chromium (Playwright).

Le serveur tourne dans un sous-processus sur une base SQLite temporaire, sans aucun accès Google ni Gemini
(variables d'environnement vidées, prioritaires sur le .env), et le navigateur bloque toute requête hors de
localhost : aucune donnée réelle ni appel payant.

Sans Chromium utilisable, le test est ignoré ; la CI pose E2E_BROWSER_REQUIRED=1 pour qu'il échoue à la place.
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
HOME_PLACEHOLDER = "Écrire à Otis…"

# Section du menu → (feuille, placeholder de la barre ; None = feuille sans barre de saisie).
SECTIONS = {
    "courses": ("view-shopping", "Ajouter un article…"),
    "repas": ("view-meals", "Planifier un repas…"),
    "taches": ("view-tasks", "Nouvelle tâche…"),
    "sport": ("view-sport", None),  # barre d'actions seulement (décision du 16/11)
    "second_cerveau": ("view-second-brain", "Noter une idée…"),
    "journal": ("view-journal", None),
    "reglages": ("view-settings", None),
}

# Raccourcis d'URL du manifeste et des widgets → feuille du dessus attendue.
SHORTCUTS = {
    "shopping_list": "view-shopping",
    "meal_today": "view-meals",
    "sport_today": "view-sport",
    "sport_gamification": "view-sport-trophies",
    "second_brain": "view-second-brain",
}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def base_url(tmp_path_factory):
    port = _free_port()
    workdir = tmp_path_factory.mktemp("e2e")
    log_path = workdir / "server.log"
    env = {
        **os.environ,
        "SQLITE_DB_PATH": str(workdir / "hub.db"),
        "API_KEY": "",
        "GEMINI_API_KEY": "",
        "NLU_MODE": "legacy",
        "LITESTREAM_REPLICA_URL": "",
        "GOOGLE_SERVICE_ACCOUNT_FILE": str(ROOT / "absent-credentials.json"),
        "GOOGLE_SERVICE_ACCOUNT_INFO": "",
        "SPREADSHEET_MEALS_SHOPPING_ID": "",
        "SPREADSHEET_BUDGET_ID": "",
        "SPREADSHEET_SPORT_ID": "",
        "GOOGLE_OAUTH_CLIENT_ID": "",
        "GOOGLE_OAUTH_CLIENT_SECRET": "",
        "GOOGLE_OAUTH_REFRESH_TOKEN": "",
    }
    env.pop("PYTEST_CURRENT_TEST", None)
    url = f"http://127.0.0.1:{port}"
    # Sortie dans un fichier : un tuyau jamais lu se remplit et bloque le serveur au bout de quelques pages.
    with open(log_path, "w", encoding="utf-8") as log:
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    urllib.request.urlopen(f"{url}/health", timeout=1)
                    break
                except OSError:
                    if server.poll() is not None or time.monotonic() > deadline:
                        output = log_path.read_text(encoding="utf-8")
                        raise RuntimeError(f"Le serveur E2E n'a pas démarré sur {url} :\n{output[-3000:]}")
                    time.sleep(0.2)
            yield url
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as pw:
        try:
            chromium = pw.chromium.launch()
        except Exception as exc:
            message = f"Chromium indisponible (`playwright install --with-deps chromium`) : {exc}"
            if os.environ.get("E2E_BROWSER_REQUIRED"):
                pytest.fail(message)
            pytest.skip(message)
        yield chromium
        chromium.close()


@pytest.fixture
def page(browser, base_url):
    context = browser.new_context(
        viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True,
        service_workers="block", locale="fr-FR", timezone_id="Europe/Paris",
    )
    context.add_init_script("localStorage.setItem('pah_tts_enabled', 'false');")
    context.route(
        lambda url: not url.startswith(base_url) and not url.startswith(("data:", "blob:")),
        lambda route: route.abort(),
    )
    tab = context.new_page()
    tab.script_errors = []
    tab.on("pageerror", lambda exc: tab.script_errors.append(str(exc)))
    tab.goto(f"{base_url}/app")
    tab.wait_for_selector("#view-home.active")
    yield tab
    errors = tab.script_errors
    context.close()
    assert not errors, f"Erreurs JavaScript non rattrapées : {errors}"


def _is_open(page, sheet_id: str) -> bool:
    return page.get_attribute(f"#{sheet_id}", "aria-hidden") == "false"


def _wait_open(page, sheet_id: str) -> None:
    page.wait_for_selector(f"#{sheet_id}[aria-hidden='false']")


def _wait_home(page) -> None:
    page.wait_for_selector("#view-home.active")


def _composer_parent(page) -> str:
    return page.evaluate("document.getElementById('query-form').parentElement.closest('[id]').id")


def test_drawer_opens_from_the_burger_and_closes_with_escape(page):
    page.click("#btn-open-drawer")
    page.wait_for_selector("#drawer.is-open")
    assert page.get_attribute("#btn-open-drawer", "aria-expanded") == "true"
    page.keyboard.press("Escape")
    page.wait_for_selector("#drawer:not(.is-open)")
    assert page.get_attribute("#btn-open-drawer", "aria-expanded") == "false"


@pytest.mark.parametrize("section", SECTIONS)
def test_each_drawer_entry_opens_its_sheet_and_escape_returns_home(page, section):
    sheet_id, placeholder = SECTIONS[section]
    page.click("#btn-open-drawer")
    page.click(f".drawer__item[data-section='{section}']")
    _wait_open(page, sheet_id)

    assert not page.evaluate("document.getElementById('view-home').classList.contains('active')")
    assert page.get_attribute(f".drawer__item[data-section='{section}']", "aria-current") == "page"
    if placeholder is not None:
        assert _composer_parent(page) == sheet_id
        assert page.get_attribute("#query-input", "placeholder") == placeholder

    page.keyboard.press("Escape")
    _wait_home(page)
    assert not _is_open(page, sheet_id)
    assert _composer_parent(page) == "composer-home-slot"
    assert page.get_attribute("#query-input", "placeholder") == HOME_PLACEHOLDER


def test_home_bubble_and_recent_actions_open_their_sheets(page):
    page.click("#bubble-taches")
    _wait_open(page, "view-tasks")
    assert page.get_attribute("#query-input", "placeholder") == "Nouvelle tâche…"
    page.keyboard.press("Escape")
    _wait_home(page)

    page.click("[data-open-conversation]")
    _wait_open(page, "view-conversation")
    page.keyboard.press("Escape")
    _wait_home(page)


def test_stacked_sheet_closes_alone_then_its_section(page):
    page.click("#bubble-sport")
    _wait_open(page, "view-sport")
    page.click("#btn-sport-trophies")
    _wait_open(page, "view-sport-trophies")
    assert _is_open(page, "view-sport")

    page.keyboard.press("Escape")
    page.wait_for_selector("#view-sport-trophies[aria-hidden='true']")
    assert _is_open(page, "view-sport")

    page.keyboard.press("Escape")
    _wait_home(page)
    assert not _is_open(page, "view-sport")


@pytest.mark.parametrize("action,sheet_id", SHORTCUTS.items())
def test_url_shortcuts_open_the_right_sheet(page, base_url, action, sheet_id):
    page.goto(f"{base_url}/app?action={action}")
    _wait_open(page, sheet_id)


def test_theme_switch_applies_and_persists_across_reloads(page):
    initial = page.get_attribute("html", "data-theme")
    page.click("#btn-open-drawer")
    page.click("label.drawer__item:has(#theme-switch)")
    toggled = page.get_attribute("html", "data-theme")
    assert toggled in ("light", "dark") and toggled != initial

    page.reload()
    _wait_home(page)
    assert page.get_attribute("html", "data-theme") == toggled
