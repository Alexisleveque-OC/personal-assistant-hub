"""PWA : « Réglages & voix » passe de l'ancienne modale à une feuille (refonte UX, étape 7 suite ; contenu inchangé).

Voix (choix + écoute), micro (push-to-talk, mains-libres, délai de silence), clé d'API, modèle & quotas Gemini,
« Enregistrer ». Logique sortie d'app.js dans views/settings_view.js.
"""
import re

from fastapi.testclient import TestClient

from app.main import app
from tests.js_helpers import rendered_html, section

client = TestClient(app)


def _static(path: str) -> str:
    return client.get(f"/static/{path}").text


def test_settings_is_a_sheet_opened_from_the_menu_and_the_old_modal_is_gone():
    html = rendered_html()
    assert re.search(r'id="btn-settings"[^>]*data-section="reglages"', html)
    assert "settings-modal" not in html and "modal-overlay" not in html
    sheet = section(html, "view-settings")
    assert '<h2 class="sheet__title" id="view-settings-title">Réglages &amp; voix</h2>' in sheet
    assert 'data-sheet-close aria-label="Fermer"' in sheet
    for control in ('<select id="voice-select"', 'id="btn-test-voice"', 'id="push-to-talk-toggle"',
                    'id="wake-word-toggle"', '<select id="vad-silence-select"', 'type="password" id="api-key-input"',
                    'id="llm-quota-badge"', 'id="llm-stat-model"', 'id="llm-stat-requests"', 'id="llm-stat-remaining"',
                    'id="llm-stat-latency"', 'id="btn-save-settings"'):
        assert control in sheet, control
    assert re.search(r'<option value="2000" selected>', sheet)
    assert "btn-close-settings" not in sheet  # la croix de la feuille ferme sans enregistrer
    assert "composer-slot" not in sheet


def test_settings_section_and_view_module():
    assert 'reglages: { sheetId: "view-settings"' in _static("js/ui_shell.js")
    view = _static("js/views/settings_view.js")
    for needle in ("export function loadSettings(", "export function initSettingsView(", "llmStatsView(",
                   "fetchLlmStats(", "populateVoiceList(", "setupMicButtonBehavior(", "setWakeWordEnabled(",
                   "pah_api_key", "pah_voice_uri", "pah_push_to_talk", "pah_vad_silence_ms", "showToastSuccess("):
        assert needle in view, needle
    assert "innerHTML" not in view and "appendAssistantMessage" not in view
    js = (_static("app.js") + _static("js/app_shell.js"))
    assert "loadSettings()" in js and "initSettingsView(" in js
    assert "settingsModal" not in js and "refreshLlmStats" not in js


def test_styles_cover_the_settings_sheet():
    css = _static("styles/app.css")
    for selector in (".settings-form", ".settings-group", ".settings-row", ".settings-stats", ".settings__footer"):
        assert selector in css, selector
