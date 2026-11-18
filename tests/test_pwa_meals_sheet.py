"""PWA : feuille « Repas » (refonte UX, ROADMAP étape 6, maquette E-Repas ; décisions utilisateur du 17/11).

Navigation ‹ › de semaine en semaine (onglet annuel « repas AAAA », retours du 17/11), bande des 7 jours (toucher un
jour fait défiler jusqu'à sa carte), les 7 jours en cartes Midi / Soir, « Ajouter » pré-remplit la barre,
« Demander une idée à Otis » sur un jour vide, ingrédients de la semaine affichée à cocher puis envoyés à Otis.
Lecture directe GET /api/v1/meals/week?offset=N : plus de question à Otis à l'ouverture.
"""
import re

from fastapi.testclient import TestClient

from app.main import app
from tests.js_helpers import rendered_html, section

client = TestClient(app)


def test_meals_sheet_has_a_day_strip_cards_and_the_ingredients_button():
    sheet = section(rendered_html(), "view-meals")
    assert 'id="meal-nav"' in sheet
    assert sheet.index('id="meal-nav"') < sheet.index('id="meal-days"')
    assert re.search(r'id="meal-days"[^>]*role="tablist"[^>]*aria-label="Jour"', sheet)
    assert 'id="meal-container"' in sheet
    assert re.search(r'<button type="button"[^>]*id="btn-meal-ingredients"[^>]*aria-expanded="false"', sheet)
    assert "Ingrédients de la semaine → courses" in sheet
    assert re.search(r'id="meal-ingredients"[^>]*hidden', sheet)
    assert 'class="composer-slot"' in sheet
