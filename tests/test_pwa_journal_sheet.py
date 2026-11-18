"""PWA : feuille « Journal & feedback » rhabillée (refonte UX, étape 7 suite ; contenu inchangé).

Vue DOM sans innerHTML ni alert, données de journal_model.js, correction dépliable « Corriger » sous chaque échange.
"""
import re

from fastapi.testclient import TestClient

from app.main import app
from tests.js_helpers import rendered_html

client = TestClient(app)


def test_journal_sheet_lists_exchanges():
    html = rendered_html()
    start = html.index('id="view-journal"')
    sheet = html[start:html.index("</section>", start)]
    assert re.search(r'id="audit-logs-list" class="journal-list"', sheet)
