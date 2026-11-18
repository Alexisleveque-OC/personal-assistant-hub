"""Refonte UX (ROADMAP Étape 2) : feuille Sport — barre d'actions, vues, détail et formulaire en feuilles empilées,
séance ouverte transmise à Otis, dictée vers la route brouillon."""
import re

from fastapi.testclient import TestClient

from app.main import app
from tests.js_helpers import STATIC, rendered_html, run_node, section

client = TestClient(app)


def _run_shell(snippet: str):
    return run_node((STATIC / "js" / "ui_shell.js").read_text(encoding="utf-8") + "\n" + snippet)


# ---------- Feuilles empilées : section, placeholder ----------

def test_stacked_sport_sheets_belong_to_the_sport_section_with_their_own_placeholder():
    out = _run_shell("""
console.log(JSON.stringify([
  sectionForSheet("view-sport-session"), sectionForSheet("view-sport-form"),
  placeholderForSheet("view-sport-session"), placeholderForSheet("view-shopping"), placeholderForSheet(null),
]));
""")
    assert out == ["sport", "sport", "« En fait c'était 48 minutes »", "Ajouter un article…", "Écrire à Otis…"]


# ---------- Balisage ----------

def test_sport_sheet_has_view_pills_trophies_and_the_action_bar_instead_of_the_composer():
    sport = section(rendered_html(), "view-sport")

    for label in ("Semaine", "Mois · Année", "Séances"):
        assert f">{label}</button>" in sport
    assert sport.count('role="tab"') >= 3
    assert 'aria-label="Trophées"' in sport
    assert 'class="action-bar"' in sport
    assert "Dicter une séance" in sport
    assert 'aria-label="Saisir une séance à la main"' in sport
    assert 'aria-label="Importer une capture de montre"' in sport
    assert "composer-slot" not in sport
    for container in ("sport-week", "sport-period", "sport-sessions-list"):
        assert f'id="{container}"' in sport


def test_session_detail_is_a_stacked_sheet_holding_the_composer():
    detail = section(rendered_html(), "view-sport-session")

    assert 'class="sheet sheet--stacked"' in client.get("/app").text.split('id="view-sport-session"')[0][-80:]
    assert 'aria-label="Retour aux séances"' in detail
    assert ">Modifier<" in detail or "Modifier</button>" in detail
    assert 'aria-label="Supprimer la séance"' in detail
    assert 'class="composer-slot"' in detail


def test_session_form_is_a_stacked_sheet_with_the_dictation_callout():
    html = rendered_html()
    form = section(html, "view-sport-form")

    assert 'class="sheet sheet--stacked"' in html.split('id="view-sport-form"')[0][-80:]
    assert "Dicte ta séance" in form
    assert 'aria-label="Dicter pour remplir le formulaire"' in form
    assert ">Annuler</button>" in form and ">OK</button>" in form and ">Enregistrer</button>" in form
    assert "composer-slot" not in form
    for field in ("sport-form-date", "sport-form-distance", "sport-form-dplus", "sport-form-h", "sport-form-m",
                  "sport-form-s", "sport-form-rpe", "sport-form-meteo", "sport-form-fc-moy", "sport-form-fc-max",
                  "sport-form-remarques", "sport-form-programme", "sport-form-pain", "sport-form-pain-level",
                  "sport-form-pain-zone"):
        assert f'id="{field}"' in form, field
    # Notes en pastilles sur une rangée (retour téléphone du 16/11 : les curseurs bougeaient au défilement)
    assert 'type="range"' not in form
    assert form.count('class="scale') == 3 and form.count('role="radiogroup"') == 3


def test_each_scale_has_its_value_label():
    form = section(rendered_html(), "view-sport-form")

    for scale in re.findall(r'class="scale[^"]*" id="([^"]+)"', form):
        assert f'id="{scale}-value"' in form, f"étiquette {scale}-value absente"


# ---------- Contexte transmis à Otis ----------

# ---------- Dictée d'une séance ----------

# ---------- Service worker ----------
