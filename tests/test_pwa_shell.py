"""Refonte UX (ROADMAP Étape 0, socle) : registre des sections, thème, raccourcis et gestion des feuilles.

Les modules JS sans import sont exécutés sous Node (même principe que test_voice_diag_log.py)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
WINDOWS_NODE = Path("/mnt/c/Program Files/nodejs/node.exe")
NODE = shutil.which("node") or (str(WINDOWS_NODE) if WINDOWS_NODE.exists() else None)

# DOM minimal : juste ce que sheets.js manipule (classes, attributs, focus, inert).
FAKE_DOM = """
const doc = { activeElement: null };
class FakeClassList {
  constructor() { this.set = new Set(); }
  add(...c) { c.forEach((x) => this.set.add(x)); }
  remove(...c) { c.forEach((x) => this.set.delete(x)); }
  contains(c) { return this.set.has(c); }
  toggle(c, force) { const on = force === undefined ? !this.set.has(c) : force; on ? this.set.add(c) : this.set.delete(c); return on; }
}
class FakeEl {
  constructor(id) { this.id = id; this.classList = new FakeClassList(); this.attrs = {}; this.inert = false; this.style = {}; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  removeAttribute(k) { delete this.attrs[k]; }
  hasAttribute(k) { return k in this.attrs; }
  focus() { doc.activeElement = this; }
}
const els = {};
for (const id of ["app", "drawer", "backdrop", "burger", "view-shopping", "view-sport", "sheet-session", "bubble"]) els[id] = new FakeEl(id);
const manager = createSheetManager({
  getSheet: (id) => els[id] || null,
  app: els.app, drawer: els.drawer, backdrop: els.backdrop, burger: els.burger,
});
const state = (id) => ({ open: els[id].classList.contains("is-open"), hidden: els[id].getAttribute("aria-hidden") });
"""


def _run(module: str, snippet: str, prelude: str = "") -> dict:
    if not NODE:
        pytest.skip("Node.js indisponible pour exécuter le module JS")
    source = (STATIC / "js" / module).read_text(encoding="utf-8") + "\n" + prelude + "\n" + snippet
    result = subprocess.run([NODE, "--input-type=module"], input=source, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


# ---------- ui_shell.js : données pures ----------

def test_each_section_has_its_sheet_placeholder_and_otis_context():
    out = _run("ui_shell.js", "console.log(JSON.stringify(SECTIONS));")

    assert out["accueil"] == {"sheetId": None, "title": "Accueil", "placeholder": "Écrire à Otis…", "context": "accueil"}
    assert out["courses"]["sheetId"] == "view-shopping" and out["courses"]["placeholder"] == "Ajouter un article…"
    assert out["repas"]["sheetId"] == "view-meals" and out["repas"]["placeholder"] == "Planifier un repas…"
    assert out["taches"]["sheetId"] == "view-tasks" and out["taches"]["placeholder"] == "Nouvelle tâche…"
    assert out["second_cerveau"]["sheetId"] == "view-second-brain"
    assert out["second_cerveau"]["placeholder"] == "Noter une idée…"
    assert out["sport"]["sheetId"] == "view-sport"
    assert {key: s["context"] for key, s in out.items()} == {
        "accueil": "accueil", "courses": "courses", "repas": "repas", "taches": "taches",
        "sport": "sport", "second_cerveau": "second_cerveau",
    }


def test_section_is_found_back_from_its_sheet():
    out = _run("ui_shell.js", """
console.log(JSON.stringify([sectionForSheet("view-sport"), sectionForSheet(null), sectionForSheet("inconnue")]));
""")
    assert out == ["sport", "accueil", "accueil"]


def test_theme_uses_the_saved_choice_then_the_system_preference():
    out = _run("ui_shell.js", """
console.log(JSON.stringify([
  resolveTheme("light", true), resolveTheme("dark", false),
  resolveTheme(null, true), resolveTheme(null, false), resolveTheme("bleu", true),
]));
""")
    assert out == ["light", "dark", "dark", "light", "dark"]


def test_url_shortcuts_open_the_matching_section():
    out = _run("ui_shell.js", """
console.log(JSON.stringify(["shopping_list", "meal_today", "sport_today", "sport_gamification", "second_brain", "inconnu", null]
  .map(sectionForAction)));
""")
    assert out == [
        {"section": "courses", "subview": None},
        {"section": "repas", "subview": None},
        {"section": "sport", "subview": None},
        {"section": "sport", "subview": "gamification"},
        {"section": "second_cerveau", "subview": None},
        None,
        None,
    ]


def test_greeting_and_date_of_the_top_bar():
    out = _run("ui_shell.js", """
const morning = new Date(2026, 10, 10, 9, 0);
const evening = new Date(2026, 10, 10, 18, 0);
console.log(JSON.stringify([greetingFor(morning), greetingFor(evening), formatLongDate(evening)]));
""")
    assert out == ["Bonjour", "Bonsoir", "Mardi 10 novembre"]


# ---------- sheets.js : pile des feuilles et menu ----------

def test_opening_a_sheet_shows_it_hides_the_home_and_focuses_the_sheet():
    out = _run("sheets.js", """
manager.openSheet("view-shopping", els.bubble);
console.log(JSON.stringify({
  sheet: state("view-shopping"), active: els["view-shopping"].classList.contains("active"),
  backdrop: els.backdrop.classList.contains("is-open"), appInert: els.app.inert,
  focus: doc.activeElement.id, top: manager.topSheetId(),
}));
""", FAKE_DOM)
    assert out == {
        "sheet": {"open": True, "hidden": "false"}, "active": True, "backdrop": True, "appInert": True,
        "focus": "view-shopping", "top": "view-shopping",
    }


def test_closing_a_sheet_gives_the_focus_back_to_its_trigger():
    out = _run("sheets.js", """
manager.openSheet("view-shopping", els.bubble);
manager.closeTop();
console.log(JSON.stringify({
  sheet: state("view-shopping"), active: els["view-shopping"].classList.contains("active"),
  backdrop: els.backdrop.classList.contains("is-open"), appInert: els.app.inert,
  focus: doc.activeElement.id, top: manager.topSheetId(),
}));
""", FAKE_DOM)
    assert out == {
        "sheet": {"open": False, "hidden": "true"}, "active": False, "backdrop": False, "appInert": False,
        "focus": "bubble", "top": None,
    }


def test_stacked_sheet_closes_alone_and_the_one_below_becomes_interactive_again():
    out = _run("sheets.js", """
manager.openSheet("view-sport", els.bubble);
const sportTrigger = new FakeEl("session-card");
manager.openSheet("sheet-session", sportTrigger);
const stacked = { sportInert: els["view-sport"].inert, top: manager.topSheetId() };
manager.closeTop();
console.log(JSON.stringify({
  stacked, sport: state("view-sport"), sportInert: els["view-sport"].inert,
  focus: doc.activeElement.id, top: manager.topSheetId(),
}));
""", FAKE_DOM)
    assert out == {
        "stacked": {"sportInert": True, "top": "sheet-session"},
        "sport": {"open": True, "hidden": "false"}, "sportInert": False,
        "focus": "session-card", "top": "view-sport",
    }


def test_opening_a_section_from_another_replaces_it_instead_of_stacking():
    out = _run("sheets.js", """
manager.openSheet("view-sport", els.bubble);
manager.openSection("view-shopping", els.burger);
console.log(JSON.stringify({ sport: state("view-sport"), shopping: state("view-shopping"), top: manager.topSheetId() }));
""", FAKE_DOM)
    assert out == {
        "sport": {"open": False, "hidden": "true"},
        "shopping": {"open": True, "hidden": "false"},
        "top": "view-shopping",
    }


def test_drawer_opens_with_aria_expanded_and_escape_closes_it_first():
    out = _run("sheets.js", """
manager.openSheet("view-sport", els.bubble);
manager.openDrawer();
const opened = { drawer: els.drawer.classList.contains("is-open"), expanded: els.burger.getAttribute("aria-expanded") };
manager.handleEscape();
console.log(JSON.stringify({
  opened, drawer: els.drawer.classList.contains("is-open"), expanded: els.burger.getAttribute("aria-expanded"),
  sportStillOpen: state("view-sport").open, focus: doc.activeElement.id,
}));
""", FAKE_DOM)
    assert out == {
        "opened": {"drawer": True, "expanded": "true"},
        "drawer": False, "expanded": "false", "sportStillOpen": True, "focus": "burger",
    }


def test_escape_without_drawer_closes_the_top_sheet_and_unknown_sheet_fails_loudly():
    out = _run("sheets.js", """
manager.openSheet("view-sport", els.bubble);
manager.handleEscape();
let error = null;
try { manager.openSheet("view-absente"); } catch (e) { error = e.message; }
console.log(JSON.stringify({ sport: state("view-sport").open, error }));
""", FAKE_DOM)
    assert out["sport"] is False
    assert "view-absente" in out["error"]


def test_listeners_are_told_which_sheet_is_on_top():
    out = _run("sheets.js", """
const seen = [];
manager.onChange((top) => seen.push(top));
manager.openSheet("view-sport", els.bubble);
manager.openSheet("sheet-session", els.bubble);
manager.closeAll();
console.log(JSON.stringify(seen));
""", FAKE_DOM)
    assert out == ["view-sport", "sheet-session", None]


# ---------- Page servie : structure et accessibilité ----------

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)
SHEETS = {
    "view-shopping": "Courses", "view-tasks": "Tâches", "view-meals": "Repas",
    "view-sport": "Sport", "view-second-brain": "Second cerveau",
}


def _rendered_html() -> str:
    import re
    return re.sub(r"<!--.*?-->", "", client.get("/app").text, flags=re.DOTALL)


def test_tab_bar_is_replaced_by_a_burger_menu_listing_every_section():
    html = _rendered_html()

    assert 'class="bottom-nav"' not in html and "nav-item" not in html
    assert 'id="btn-open-drawer"' in html and 'aria-controls="drawer"' in html
    assert '<nav class="drawer" id="drawer" aria-label="Menu principal"' in html
    for section in ("accueil", "courses", "repas", "taches", "sport", "second_cerveau"):
        assert f'data-section="{section}"' in html
    assert 'id="drawer-journal"' in html and 'id="btn-settings"' in html and 'id="theme-switch"' in html


def test_each_section_is_an_accessible_sheet_with_a_close_button_and_a_composer_slot():
    import re
    html = _rendered_html()

    for sheet_id, title in SHEETS.items():
        match = re.search(rf'<section class="sheet" id="{sheet_id}"([^>]*)>(.*?)\n    </section>', html, re.S)
        assert match, f"feuille {sheet_id} absente"
        attrs, body = match.groups()
        assert 'role="dialog"' in attrs and 'aria-modal="true"' in attrs
        assert f'aria-labelledby="{sheet_id}-title"' in attrs
        assert f'<h2 class="sheet__title" id="{sheet_id}-title">{title}</h2>' in body
        assert 'data-sheet-close aria-label="Fermer"' in body
        assert '<div class="composer-slot"></div>' in body


def test_a_single_universal_composer_with_photo_and_hold_to_talk_mic():
    html = _rendered_html()

    assert html.count('class="composer"') == 1
    assert html.count('id="mic-btn"') == 1 and 'class="mic-btn"' in html
    assert 'aria-label="Maintenir pour parler à Otis"' in html
    assert 'aria-label="Envoyer une photo"' in html
    assert 'placeholder="Écrire à Otis…"' in html


def test_new_styles_and_modules_are_served_and_precached():
    html = client.get("/app").text
    sw = client.get("/sw.js").text

    for path in ("/static/styles/hub.css", "/static/styles/app.css", "/static/styles/legacy-bridge.css",
                 "/static/js/ui_shell.js", "/static/js/sheets.js"):
        res = client.get(path)
        assert res.status_code == 200, path
        assert f'"{path}"' in sw, f"{path} absent du cache du service worker"
    for css in ("hub.css", "app.css", "legacy-bridge.css"):
        assert f"/static/styles/{css}" in html
    assert "pah-pwa-cache-v33" in sw


def test_theme_is_set_before_first_paint_from_saved_choice_or_system():
    html = client.get("/app").text
    head = html[:html.index("</head>")]

    assert 'localStorage.getItem("pah_theme")' in head
    assert "prefers-color-scheme: dark" in head


# ---------- Retour téléphone du 10/11 : vieux JS servi par le cache HTTP, barre du haut qui défile ----------

def test_static_files_are_revalidated_instead_of_heuristically_cached():
    for path in ("/static/app.js", "/static/js/config.js", "/static/styles/hub.css"):
        res = client.get(path)
        assert res.status_code == 200
        assert res.headers.get("cache-control") == "no-cache", path
        assert res.headers.get("etag"), path


def test_service_worker_bypasses_the_http_cache_when_it_fetches_assets():
    sw = client.get("/sw.js").text

    assert "pah-pwa-cache-v33" in sw
    assert 'new Request(url, { cache: "reload" })' in sw  # précache à l'installation
    assert sw.count('fetch(event.request, { cache: "no-cache" })') == 2  # JS réseau d'abord + autres assets


def test_top_bar_stays_visible_while_the_home_scrolls():
    css = client.get("/static/styles/app.css").text

    assert ".topbar {" in css and "position: sticky;" in css and "top: 0;" in css
