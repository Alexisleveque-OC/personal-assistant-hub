"""PWA : bulle « Otis réfléchit… » pendant l'attente de la réponse (Étape 7, décision du 27/10/2026).

Un tour agent prend plusieurs secondes : l'indicateur montre qu'il se passe quelque chose (et que ce n'est pas un bug).
"""
import re

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _body_of(js: str, function_name: str) -> str:
    start = js.index(f"export async function {function_name}(")
    following = js.find("\nexport ", start + 1)
    return js[start:following if following != -1 else len(js)]


def test_chat_shows_thinking_bubble_while_waiting_for_text_and_voice_replies():
    js = client.get("/static/js/views/chat_view.js").text

    assert "Otis réfléchit" in js
    for function_name in ("sendInteraction", "sendAudioInteraction"):
        body = _body_of(js, function_name)
        assert "showThinkingIndicator()" in body, function_name
        # Retirée quoi qu'il arrive (réponse, erreur HTTP, panne réseau) : jamais de bulle orpheline.
        assert re.search(r"finally\s*\{\s*hideThinkingIndicator\(\);", body), function_name


def test_thinking_bubble_is_styled_and_animated():
    css = client.get("/static/styles/app.css").text  # refonte : plus de dépendance à l'ancien style.css

    assert ".msg--thinking" in css
    assert "@keyframes msg-dot" in css
