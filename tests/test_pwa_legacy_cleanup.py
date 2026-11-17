"""Refacto anti-tokens, lot 1 : l'ancien style.css, le pont legacy-bridge.css, le calibrage du mot « Otis »
et le code commenté disparaissent ; les composants encore vivants de l'ancien style sont repris dans app.css."""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"


def _read(rel: str) -> str:
    return (STATIC / rel).read_text(encoding="utf-8")


def test_legacy_stylesheets_and_backgrounds_are_gone():
    for rel in ("style.css", "styles/legacy-bridge.css", "images/bg-dark.png", "images/bg-light.png"):
        assert not (STATIC / rel).exists(), rel
    html, sw = _read("index.html"), _read("sw.js")
    for ref in ("/static/style.css", "legacy-bridge.css", "Plus+Jakarta+Sans", "botanical"):
        assert ref not in html, ref
    assert "/static/style.css" not in sw and "legacy-bridge.css" not in sw


def test_toast_container_uses_the_new_stack_class():
    html = _read("index.html")
    assert re.search(r'<div id="toast-container" class="toast-stack"', html)


def test_index_html_has_no_commented_out_markup():
    html = _read("index.html")
    for comment in re.findall(r"<!--(.*?)-->", html, re.S):
        assert "<div" not in comment and "<button" not in comment, comment[:80]


def test_wake_word_calibration_is_removed_but_saved_variants_still_match():
    html, app_js, speech = _read("index.html"), _read("app.js"), _read("js/speech.js")
    assert "wake-calibration-section" not in html and "btn-start-calibration" not in html
    for name in ("startWakeWordCalibration", "addCustomWakeVariant", "removeCustomWakeVariant"):
        assert name not in app_js and name not in speech, name
    # Variantes déjà enregistrées sur le téléphone : toujours reconnues.
    assert "state.wakeWordCustomVariants" in speech


def test_app_js_has_no_commented_out_code():
    app_js = _read("app.js")
    assert not re.search(r"^\s*//\s*(const|let|if \(|\}|\w+\(.*\);)", app_js, re.M)


def test_new_styles_keep_the_reset_and_the_runtime_components_of_the_old_style():
    hub, app_css = _read("styles/hub.css"), _read("styles/app.css")
    assert re.search(r"\*\s*\{[^}]*margin:\s*0;[^}]*padding:\s*0;", hub)
    for selector in (
        ".voice-bar-area.active",
        ".visual-bar",
        ".interim-transcript",
        ".wake-word-indicator.listening .wake-dot",
        ".wake-word-indicator.paused .wake-dot",
        ".wake-word-indicator.triggered",
        ".offline-outbox-badge",
        ".modal-overlay",
        ".modal-box",
    ):
        assert selector in app_css, selector
    assert "@keyframes equalize" in app_css and "@keyframes pulse-outbox" in app_css


def test_screenshot_date_modal_uses_design_system_controls():
    js = _read("js/screenshot_import.js")
    assert 'class="btn btn--primary" data-action="confirm"' in js
    assert 'class="input"' in js
    assert "--color-" not in js and "btn-secondary" not in js and "form-input" not in js
