"""PWA : feuille « Journal & feedback » rhabillée (refonte UX, étape 7 suite ; contenu inchangé).

Vue DOM sans innerHTML ni alert, données de journal_model.js, correction dépliable « Corriger » sous chaque échange.
"""
import re

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _rendered_html() -> str:
    return re.sub(r"<!--.*?-->", "", client.get("/app").text, flags=re.DOTALL)


def _static(path: str) -> str:
    return client.get(f"/static/{path}").text


def test_journal_sheet_lists_exchanges():
    html = _rendered_html()
    start = html.index('id="view-journal"')
    sheet = html[start:html.index("</section>", start)]
    assert re.search(r'id="audit-logs-list" class="journal-list"', sheet)


def test_journal_view_uses_the_model_and_renders_without_html_injection():
    view = _static("js/views/journal_view.js")
    for needle in ("logCard(", "feedbackPayload(", "fetchConversationLogs(", "postConversationFeedback(",
                   "Corriger", "Envoyer", "Annuler", "aria-expanded", "Correction enregistrée", "showToastError("):
        assert needle in view, needle
    for forbidden in ("innerHTML", "alert(", "user_prompt", "matched_by", "error_message", "log.status"):
        assert forbidden not in view, forbidden


def test_new_modules_are_precached_and_versions_bumped():
    sw = client.get("/sw.js").text
    assert '"/static/js/db_date.js"' in sw and '"/static/js/journal_model.js"' in sw
    assert "pah-pwa-cache-v49" in sw
    assert "/static/app.js?v=31.0" in _rendered_html()


def test_styles_cover_the_journal_cards():
    css = _static("styles/app.css")
    for selector in (".journal-list", ".journal-card", ".journal-card__head", ".journal-card__dot--ok",
                     ".journal-card__dot--ko", ".journal-card__intent", ".journal-card__line", ".journal-card__foot",
                     ".journal-card__form"):
        assert selector in css, selector
