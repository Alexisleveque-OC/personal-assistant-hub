"""Refacto anti-tokens, lot 1 : l'ancien style.css, le pont legacy-bridge.css, le calibrage du mot « Otis »
et le code commenté disparaissent ; les composants encore vivants de l'ancien style sont repris dans app.css."""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"


def _read(rel: str) -> str:
    return (STATIC / rel).read_text(encoding="utf-8")


def test_toast_container_uses_the_new_stack_class():
    html = _read("index.html")
    assert re.search(r'<div id="toast-container" class="toast-stack"', html)


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
