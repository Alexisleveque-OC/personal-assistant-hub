"""Test E2E de l'import Swile par captures (Phase 10, étape 8) dans un vrai Chromium (Playwright).

Bouton « Importer Swile » de l'écran Budget → capture choisie → relecture (doublon décoché, ligne sans catégorie,
crédit, solde « ancien → nouveau ») → « Importer » → lignes dans `Swile` / `Revenus` et solde dans `Gestion` → toast
« Annuler » qui retire tout. Gemini n'est jamais appelé (lecture simulée) ; le classeur est une doublure en mémoire :
les requêtes du navigateur sont rejouées sur l'application (TestClient), comme dans test_e2e_budget_screen.py.
"""
import re
from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.connectors.sheets.budget_connector import BudgetConnector
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.dependencies import set_budget_connector, set_sport_connector
from app.core.swile_import.models import SwileCapture, SwileCaptureLine
from app.main import app
from tests.budget_fakes import BudgetSheetState, build_budget_spreadsheet
from tests.test_e2e_navigation import base_url, browser, e2e_server, page  # noqa: F401 (fixtures)
from tests.test_swile_review_api import ANALYZE, STATE, reste_swile_value, set_reste_swile

CAPTURE = SwileCapture(is_swile=True, solde=95.64, lignes=[
    SwileCaptureLine(marchand="Intermarche", date_texte="mercredi 25 nov. 2026, 17:35", montant=-12.81),
    SwileCaptureLine(marchand="Maryann", date_texte="lundi 23 nov. 2026, 12:52", montant=-6.9),
    SwileCaptureLine(marchand="Intermarche", date_texte="samedi 21 nov. 2026, 10:27", montant=-25.0),
    SwileCaptureLine(marchand="Crédit titres-resto", date_texte="vendredi 6 nov. 2026, 04:13", montant=242.0),
    SwileCaptureLine(marchand="Fnac", date_texte="jeudi 29", montant=-20.0),
])


def _rows(sheet, title):
    values = sheet.worksheet(title).get_all_values(value_render_option="UNFORMATTED_VALUE")[1:]
    return [r for r in values if any(str(c).strip() for c in r)]


@pytest.fixture
def swile_sheet(page, isolate_sqlite_database):
    state = BudgetSheetState(
        groups=STATE.groups, categories=STATE.categories, auto_sort=STATE.auto_sort,
        swile=((date(2026, 11, 22), 25.0, "Course", "Otis : courses"),),
    )
    sheet = build_budget_spreadsheet(state)
    set_reste_swile(sheet, 80.0)
    set_budget_connector(BudgetConnector(sheet, today=lambda: date(2026, 11, 26)))
    set_sport_connector(SqlSportConnector(db_manager=isolate_sqlite_database))  # exigé par le service d'annulation
    client = TestClient(app)
    analyzed = []

    def replay(route):
        request = route.request
        path = request.url.split("://", 1)[1].split("/", 1)[1]
        if path.startswith("api/v1/budget/swile/analyze"):
            analyzed.append(path)
            # Corps multipart non rejoué : une capture, lue par la vision simulée.
            with patch(ANALYZE, side_effect=[CAPTURE]):
                res = client.post("/" + path, files=[("files", ("capture.jpg", b"img", "image/jpeg"))])
        else:
            res = client.request(request.method, "/" + path, content=request.post_data,
                                 headers={"Content-Type": "application/json"})
        route.fulfill(status=res.status_code, content_type="application/json", body=res.text)

    page.route("**/api/v1/budget/**", replay)
    page.route("**/api/v1/home/recent-actions/*/undo*", replay)
    yield sheet, analyzed
    set_sport_connector(None)


def test_swile_capture_is_reviewed_imported_then_undone_from_the_toast(page, swile_sheet):
    sheet, analyzed = swile_sheet
    page.click("#btn-open-drawer")
    page.click(".drawer__item[data-section='budget']")
    page.wait_for_selector("#view-budget[aria-hidden='false'] .budget-summary")
    assert page.get_attribute("#btn-budget-swile", "aria-label") == "Importer Swile"

    page.set_input_files("#budget-swile-file", files=[{"name": "capture.jpg", "mimeType": "image/jpeg", "buffer": b"img"}])
    page.wait_for_selector("#view-budget-swile[aria-hidden='false'] .budget-swile__line")
    assert re.search(r"reference_date=\d{4}-\d{2}-\d{2}", analyzed[0])  # jour local de l'import (dates relatives)

    assert "Fnac" in page.text_content("#budget-swile-warnings")
    assert page.text_content("#budget-swile-balance").replace("\xa0", " ") == "Reste Swile (novembre 2026) : 80 € → 95,64 €"
    lines = page.locator(".budget-swile__line")
    assert lines.count() == 4
    duplicate = lines.nth(2)
    assert not duplicate.locator("input[type='checkbox']").is_checked()
    assert "déjà saisie le 22/11 (Course) ?" in duplicate.text_content()
    assert lines.nth(0).locator(".budget-swile__category").input_value() == "Course"
    assert lines.nth(3).locator(".budget-swile__category").input_value() == "Ticket resto"
    submit = page.locator("#btn-budget-swile-import")
    assert submit.text_content() == "Importer 3 lignes et le solde"

    submit.click()
    assert "Maryann (23/11) : choisis une catégorie." in page.text_content("#budget-swile-errors")
    assert [r[3] for r in _rows(sheet, "Swile")] == ["Otis : courses"]  # rien d'écrit

    maryann = lines.nth(1).locator(".budget-swile__category")
    maryann.fill("resta")
    lines.nth(1).locator("[role='option']:has-text('Restaurant')").click()
    assert maryann.input_value() == "Restaurant"
    submit.click()

    page.wait_for_selector("#view-budget-swile[aria-hidden='true']", state="attached")
    toast = page.locator(".notice--success").filter(has_text="Import Swile : 3 lignes, solde 95,64 €")
    toast.wait_for()
    assert [r[3] for r in _rows(sheet, "Swile")] == ["Otis : courses", "Swile : Intermarche", "Swile : Maryann"]
    assert [r[4] for r in _rows(sheet, "Revenus")] == ["Swile : Crédit titres-resto"]
    assert reste_swile_value(sheet) == 95.64

    toast.locator(".btn-undo-action").click()
    page.locator(".notice--success").filter(has_text="C'est annulé").wait_for()
    assert len(_rows(sheet, "Swile")) == 1 and _rows(sheet, "Revenus") == []
    assert reste_swile_value(sheet) == 80.0
    assert not page.script_errors


def test_unreadable_captures_show_the_server_reason(page, swile_sheet):
    page.route("**/api/v1/budget/swile/analyze**", lambda route: route.fulfill(
        status=422, content_type="application/json",
        body='{"detail": "Capture 1 ignorée : Photo de chat."}'))
    page.click("#btn-open-drawer")
    page.click(".drawer__item[data-section='budget']")
    page.wait_for_selector("#view-budget[aria-hidden='false'] .budget-summary")

    page.set_input_files("#budget-swile-file", files=[{"name": "chat.jpg", "mimeType": "image/jpeg", "buffer": b"img"}])

    page.wait_for_selector("#budget-swile-errors:not([hidden])")
    assert "Photo de chat" in page.text_content("#budget-swile-errors")
    assert page.locator(".budget-swile__line").count() == 0
    assert page.is_disabled("#btn-budget-swile-import")
