"""Refonte UX (ROADMAP Étape 2) : feuille Sport — barre d'actions, vues, détail et formulaire en feuilles empilées,
séance ouverte transmise à Otis, dictée vers la route brouillon."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
WINDOWS_NODE = Path("/mnt/c/Program Files/nodejs/node.exe")
NODE = shutil.which("node") or (str(WINDOWS_NODE) if WINDOWS_NODE.exists() else None)
client = TestClient(app)

NEW_MODULES = (
    "/static/js/sport_model.js",
    "/static/js/views/sport/dom.js",
    "/static/js/views/sport/sport_sheet.js",
    "/static/js/views/sport/period_view.js",
    "/static/js/views/sport/sessions_list_view.js",
    "/static/js/views/sport/session_detail_view.js",
    "/static/js/views/sport/session_form_view.js",
)


def _run_shell(snippet: str):
    if not NODE:
        pytest.skip("Node.js indisponible pour exécuter le module JS")
    source = (STATIC / "js" / "ui_shell.js").read_text(encoding="utf-8") + "\n" + snippet
    result = subprocess.run([NODE, "--input-type=module"], input=source, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _rendered_html() -> str:
    return re.sub(r"<!--.*?-->", "", client.get("/app").text, flags=re.DOTALL)


def _section(html: str, sheet_id: str) -> str:
    start = html.index(f'id="{sheet_id}"')
    return html[start:html.index("</section>", start)]


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
    sport = _section(_rendered_html(), "view-sport")

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
    detail = _section(_rendered_html(), "view-sport-session")

    assert 'class="sheet sheet--stacked"' in client.get("/app").text.split('id="view-sport-session"')[0][-80:]
    assert 'aria-label="Retour aux séances"' in detail
    assert ">Modifier<" in detail or "Modifier</button>" in detail
    assert 'aria-label="Supprimer la séance"' in detail
    assert 'class="composer-slot"' in detail


def test_session_form_is_a_stacked_sheet_with_the_dictation_callout():
    html = _rendered_html()
    form = _section(html, "view-sport-form")

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
    form = _section(_rendered_html(), "view-sport-form")

    for scale in re.findall(r'class="scale[^"]*" id="([^"]+)"', form):
        assert f'id="{scale}-value"' in form, f"étiquette {scale}-value absente"


def test_scales_are_tap_only_radio_buttons():
    js = client.get("/static/js/views/sport/session_form_view.js").text

    assert 'setAttribute("role", "radio")' in js
    assert '"aria-checked"' in js
    assert "nextScaleValue(" in js
    assert '"pointermove"' not in js and '"input"' not in js.split("function bindScale(")[1].split("\n}")[0]


def test_old_sport_tabs_and_modals_are_gone():
    html = _rendered_html()

    for old in ("sport-segmented", "tab-sport-today", "modal-edit-sport-session", "modal-create-sport-session",
                "sport-today-container", "btn-add-sport-session-inline"):
        assert f'id="{old}"' not in html, old
    assert html.count('class="composer"') == 1


# ---------- Contexte transmis à Otis ----------

def test_open_session_is_sent_to_otis_and_cleared_outside_the_detail():
    api = client.get("/static/js/api.js").text
    config = client.get("/static/js/config.js").text
    detail = client.get("/static/js/views/sport/session_detail_view.js").text

    assert "ui_session_id: state.uiSessionId ?? null" in api
    assert "uiSessionId: null" in config
    assert "state.uiSessionId = topId === DETAIL_SHEET_ID ? openSessionId : null" in detail


# ---------- Dictée d'une séance ----------

def test_draft_route_client_posts_the_recording():
    api = client.get("/static/js/api.js").text
    start = api.index("export async function postSportSessionDraft(")
    body = api[start:api.index("\nexport ", start + 1)]

    assert '"/api/v1/sport/session/draft"' in body
    assert 'formData.append("audio_file"' in body
    assert '"Content-Type"' not in body  # multipart : le navigateur pose la frontière


def test_speech_engine_offers_a_one_shot_capture_for_the_form():
    speech = client.get("/static/js/speech.js").text

    assert "export function captureOnce(" in speech
    assert "export function stopCapture(" in speech
    assert "oneShotTarget || onAudioBlobCallback" in speech
    assert 'new CustomEvent("mic-listening"' in speech


def test_form_starts_listening_when_opened_by_dictate_and_saves_on_ok():
    form = client.get("/static/js/views/sport/session_form_view.js").text

    assert "captureOnce(" in form and "postSportSessionDraft(" in form
    assert "applyDraft(" in form and "formToPayload(" in form
    assert "createSportSession(" in form and "patchSportSessionById(" in form


# ---------- Service worker ----------

def test_new_sport_modules_are_served_and_precached():
    sw = client.get("/sw.js").text

    assert "pah-pwa-cache-v41" in sw
    for path in NEW_MODULES:
        assert client.get(path).status_code == 200, path
        assert f'"{path}"' in sw, f"{path} absent du cache du service worker"
