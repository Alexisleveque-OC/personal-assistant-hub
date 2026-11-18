"""Refonte UX (ROADMAP Étape 3) : feuille Trophées empilée sur Sport (maquette E-Trophees)."""
import json
import subprocess

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.js_helpers import NODE, STATIC, rendered_html, section

client = TestClient(app)


def _static(path: str) -> str:
    return (STATIC / path).read_text(encoding="utf-8")


def test_trophies_is_a_stacked_sheet_with_back_and_close_and_no_composer():
    html = rendered_html()
    sheet = section(html, "view-sport-trophies")

    assert 'class="sheet sheet--stacked"' in html.split('id="view-sport-trophies"')[0][-80:]
    assert 'role="dialog"' in sheet and 'aria-modal="true"' in sheet
    assert ">Trophées</h2>" in sheet
    assert 'data-sheet-close aria-label="Retour au sport"' in sheet
    assert 'id="btn-trophies-close" aria-label="Fermer"' in sheet
    assert 'id="trophies-body"' in sheet
    assert "composer-slot" not in sheet


def test_old_trophies_panel_is_gone_from_the_sport_sheet():
    sport = section(rendered_html(), "view-sport")

    assert 'id="sport-gamification-container"' not in sport
    assert 'id="btn-sport-trophies"' in sport and "aria-pressed" not in sport.split('id="btn-sport-trophies"')[1][:120]
    legacy = _static("js/views/sport_view.js")
    assert "renderSportGamification" not in legacy and "fetchSportGamification" not in legacy


def test_trophies_sheet_belongs_to_sport_without_its_own_placeholder():
    if not NODE:
        pytest.skip("Node.js indisponible pour exécuter le module JS")
    source = _static("js/ui_shell.js") + """
console.log(JSON.stringify([sectionForSheet("view-sport-trophies"), STACKED_SHEETS["view-sport-trophies"].placeholder]));"""
    result = subprocess.run([NODE, "--input-type=module"], input=source, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ["sport", None]


def test_view_uses_the_hub_trophy_classes_and_the_model():
    view = _static("js/views/sport/trophies_view.js")

    for needle in ('"trophy-grid"', "trophy__emoji", "trophy__tier", "is-locked", "is-unlocked", "just-unlocked",
                   "dataset.tier", "fun-row", "callout--warn", "Palier imminent", "Derniers exploits", "Records perso",
                   "Équivalences insolites", "Voir les légendaires 👑🪐", 'role", "tablist"', "fetchSportGamificationData",
                   "trophiesForTab", "closeAll"):
        assert needle in view, needle


def test_trophy_icon_and_shortcut_open_the_stacked_sheet():
    sheet_js = _static("js/views/sport/sport_sheet.js")
    app_js = _static("app.js")

    assert "openTrophies" in sheet_js and "sport-gamification-container" not in sheet_js
    assert 'shortcut.subview === "gamification"' in app_js and "openTrophies(" in app_js
    assert 'showSportView("trophies")' not in app_js
