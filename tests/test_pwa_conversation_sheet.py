"""PWA : fil de la feuille « Conversation » et notifications au style de la refonte (étape 7 suite, demande du 17/11).

Pas de maquette dédiée : briques du design system (puces, cartes, avatar d'Otis). Rendu DOM sans innerHTML ;
nouvelles classes (msg, notice, undo-bar) pour ne plus dépendre de l'ancien style.css (supprimé à l'étape 8).
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


def test_conversation_sheet_uses_chips_message_cards_and_an_undo_bar():
    sheet = _section(_rendered_html(), "view-conversation")
    assert re.search(r'<div class="chips chips--scroll" id="chips-container" aria-label="Suggestions">', sheet)
    assert sheet.index('id="chips-container"') < sheet.index('class="sheet__body"')  # puces fixes sous l'en-tête
    assert re.search(r'<button type="button" class="chip" id="chip-new-chat">Nouveau fil</button>', sheet)
    assert re.search(r'<button type="button" class="chip" data-query="Donne-moi la liste de courses">Liste de courses</button>', sheet)
    assert re.search(r'id="chat-stream" class="chat-stream" role="log"', sheet)
    assert 'class="msg msg--otis"' in sheet and 'class="msg__text"' in sheet
    assert re.search(r'id="undo-toast" class="undo-bar" hidden', sheet)
    for legacy in ("chip-btn", "chat-bubble", "bubble-header", "bubble-content", "Assistant Hub", "✨", "🍽️"):
        assert legacy not in sheet, legacy


def test_chat_view_renders_messages_without_html_injection():
    view = _static("js/views/chat_view.js")
    for needle in ('"msg msg--user"', '"msg msg--otis"', "msg--thinking", "Réécouter", "scrollConversationToEnd",
                   "#chips-container [data-query]"):
        assert needle in view, needle
    for forbidden in ("innerHTML", "chat-bubble", "chip-btn", "Assistant Hub"):
        assert forbidden not in view, forbidden
    assert "scrollConversationToEnd()" in _static("js/app_shell.js")


def test_undo_bar_is_shown_with_the_hidden_attribute():
    speech = _static("js/undo_bar.js")
    start = speech.index("export function showUndoToast(")
    body = speech[start:speech.index("export function hideUndoToast(")]
    assert "toast.hidden = false" in body and "style.display" not in body


def test_notifications_are_built_without_html_injection_and_with_svg_icons():
    js = _static("js/toast.js")
    for needle in ("notice notice--", "notice__icon", "notice__title", "notice__text", "notice__close",
                   "btn-undo-action", "createElementNS", "toast-stack"):
        assert needle in js, needle
    for forbidden in ("innerHTML", "✅", "❌", "⚠️", "ℹ️"):
        assert forbidden not in js, forbidden


def test_styles_cover_messages_undo_bar_and_notifications():
    css = _static("styles/app.css")
    for selector in (".chat-stream", ".msg--user", ".msg--otis", ".msg__head", ".msg__text", ".msg--thinking",
                     "@keyframes msg-dot", ".undo-bar", ".toast-stack", ".notice", ".notice--success", ".notice--error",
                     ".notice--warning", ".notice--info", ".notice__icon", ".notice__action", ".notice--leaving",
                     "prefers-reduced-motion"):
        assert selector in css, selector


def test_versions_bumped():
    assert "pah-pwa-cache-v49" in client.get("/sw.js").text
    assert "/static/app.js?v=31.0" in _rendered_html()
