"""E2E (vrai Chromium) : lien « Approfondir » sous une réponse de l'expert et bouton pause de la voix (Phase 6.10).

Les réponses de /api/v1/interact sont simulées par interception réseau (aucun appel Gemini ni Claude) ; la synthèse
vocale du navigateur est remplacée par une doublure qui « parle » jusqu'à ce qu'on l'interrompe.
"""
import json

from tests.test_e2e_navigation import base_url, browser, e2e_server, page  # noqa: F401 (fixtures)

FAKE_VOICE = """
window.__cancelled = 0;
const fakeSynth = {
  speaking: false,
  getVoices: () => [],
  cancel() { window.__cancelled += 1; },
  speak(utterance) { setTimeout(() => utterance.onstart && utterance.onstart(), 10); },
  addEventListener() {},
};
Object.defineProperty(window, "speechSynthesis", { configurable: true, get: () => fakeSynth });
"""


def _reply(text: str, reason: str) -> dict:
    return {
        "success": True, "spoken_response": text,
        "intent": {"intent": "agent", "confidence": 1.0, "parameters": {}, "raw_query": ""},
        "data": {"level": "expert", "expert": {"reason": reason, "model": "claude-sonnet-5-5", "usages": []}},
    }


def test_short_expert_answer_can_be_deepened_once_and_the_voice_can_be_cut(page):
    bodies = []
    replies = [_reply("Relève la référence sur la plaque.", "demande"), _reply("1. Dévisse les charnières.", "approfondir")]

    def fulfil(route):
        bodies.append(json.loads(route.request.post_data))
        route.fulfill(status=200, content_type="application/json", body=json.dumps(replies[len(bodies) - 1]))

    page.add_init_script(FAKE_VOICE + "localStorage.setItem('pah_tts_enabled', 'true');")
    page.reload()
    page.wait_for_selector("#view-home.active")
    page.route("**/api/v1/interact", fulfil)

    page.fill("#query-input", "Comment changer la porte de mon frigo ?")
    page.press("#query-input", "Enter")

    page.wait_for_selector("#btn-tts-stop:not([hidden])")
    page.click(".activity__head[data-open-conversation]")  # le fil complet est dans la feuille Conversation
    page.wait_for_selector(".msg--otis:has-text('Relève la référence') .msg__deepen")
    cancelled_before = page.evaluate("window.__cancelled")
    page.click("#btn-tts-stop")
    page.wait_for_selector("#btn-tts-stop[hidden]", state="attached")
    assert page.evaluate("window.__cancelled") > cancelled_before

    page.click(".msg__deepen")
    page.wait_for_selector(".msg--otis:has-text('1. Dévisse les charnières.')")

    assert bodies[1]["query"] == "Approfondis"
    assert bodies[1]["context"]["expert_detailed"] is True
    assert "expert_detailed" not in bodies[0]["context"]
    assert page.locator(".msg__deepen").count() == 0  # lien consommé, et pas de lien sous la réponse détaillée
