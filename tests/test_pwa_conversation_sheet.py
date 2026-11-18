"""PWA : fil de la feuille « Conversation » et notifications au style de la refonte (étape 7 suite, demande du 17/11).

Pas de maquette dédiée : briques du design system (puces, cartes, avatar d'Otis). Rendu DOM sans innerHTML ;
nouvelles classes (msg, notice, undo-bar) pour ne plus dépendre de l'ancien style.css (supprimé à l'étape 8).
"""
import re

from fastapi.testclient import TestClient

from app.main import app
from tests.js_helpers import rendered_html, section

client = TestClient(app)


def test_conversation_sheet_uses_chips_message_cards_and_an_undo_bar():
    sheet = section(rendered_html(), "view-conversation")
    assert re.search(r'<div class="chips chips--scroll" id="chips-container" aria-label="Suggestions">', sheet)
    assert sheet.index('id="chips-container"') < sheet.index('class="sheet__body"')  # puces fixes sous l'en-tête
    assert re.search(r'<button type="button" class="chip" id="chip-new-chat">Nouveau fil</button>', sheet)
    assert re.search(r'<button type="button" class="chip" data-query="Donne-moi la liste de courses">Liste de courses</button>', sheet)
    assert re.search(r'id="chat-stream" class="chat-stream" role="log"', sheet)
    assert 'class="msg msg--otis"' in sheet and 'class="msg__text"' in sheet
    assert re.search(r'id="undo-toast" class="undo-bar" hidden', sheet)
