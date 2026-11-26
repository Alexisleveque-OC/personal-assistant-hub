"""Phase 10, étape 8 (2/4) : POST /api/v1/budget/swile/analyze, relecture sans écriture (faux classeur, vision simulée).

Décisions utilisateur du 26/11 : catégorie pré-remplie par `Tri auto`, sinon par les noms appris ; crédit → type
« Ticket resto » ; doublon = même montant à ±3 jours dans `Swile` (ou `Revenus` pour un crédit), affiché décoché avec
« déjà saisie le JJ/MM (catégorie) ? » ; lignes identiques de plusieurs captures fusionnées ; ligne illisible ignorée
et signalée ; solde → « Reste Swile » du mois actif, montré avec la valeur actuelle.
"""
from datetime import date
from io import BytesIO
from typing import List
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.connectors.sheets.budget_connector import BudgetConnector
from app.core.dependencies import set_budget_connector
from app.core.database import get_database_manager
from app.core.swile_import.models import SwileCapture, SwileCaptureLine
from app.core.vision.gemini_vision import VisionServiceUnavailableError
from app.main import app
from tests.budget_fakes import DEFAULT_CATEGORIES, DEFAULT_GROUPS, BudgetSheetState, GestionLine, build_budget_spreadsheet

client = TestClient(app)
TODAY = date(2026, 11, 26)
ANALYZE = "app.core.vision.swile_vision_service.SwileVisionService.analyze_screenshot"

INCOME_WITH_TICKETS = tuple(
    (group, lines + (GestionLine("Ticket resto", 0.0),) if group == "Revenus" else lines) for group, lines in DEFAULT_GROUPS
)
STATE = BudgetSheetState(
    groups=INCOME_WITH_TICKETS,
    categories=DEFAULT_CATEGORIES + (("Ticket resto", date(2024, 1, 1), None),),
    auto_sort=(("intermarche", "Course"), ("burger king", "Restaurant"), ("amazon", "Loisir Alex")),
)


def install(state: BudgetSheetState = STATE):
    sheet = build_budget_spreadsheet(state)
    set_budget_connector(BudgetConnector(sheet, today=lambda: TODAY))
    return sheet


def line(marchand: str, date_texte: str, montant: float) -> SwileCaptureLine:
    return SwileCaptureLine(marchand=marchand, date_texte=date_texte, montant=montant)


def analyze(*captures: SwileCapture, reference_date: str = "2026-11-26"):
    files = [("files", (f"capture{i}.jpg", BytesIO(b"img"), "image/jpeg")) for i in range(len(captures))]
    with patch(ANALYZE, side_effect=list(captures)):
        return client.post("/api/v1/budget/swile/analyze", params={"reference_date": reference_date}, files=files)


def by_merchant(body) -> dict:
    return {l["marchand"]: l for l in body["lignes"]}


def test_lines_are_dated_categorized_and_checked_without_writing_anything():
    sheet = install()
    writes_before = sum(len(ws.writes) for ws in sheet.worksheets())

    res = analyze(SwileCapture(is_swile=True, lignes=[
        line("Intermarche", "mercredi 25 nov. 2026, 17:35", -12.81),
        line("Maryann", "lundi 23 nov. 2026, 12:52", -6.90),
        line("Crédit titres-resto", "vendredi 6 nov. 2026, 04:13", 242.0),
    ]))

    assert res.status_code == 200, res.text
    lines = by_merchant(res.json())
    assert lines["Intermarche"] == {
        "type": "depense", "date": "2026-11-25", "montant": 12.81, "marchand": "Intermarche",
        "categorie": "Course", "doublon": None, "cochee": True,
    }
    assert lines["Maryann"]["categorie"] is None  # ni Tri auto ni nom appris : à choisir à la relecture
    assert lines["Crédit titres-resto"]["type"] == "credit"
    assert lines["Crédit titres-resto"]["categorie"] == "Ticket resto"
    assert [l["date"] for l in res.json()["lignes"]] == ["2026-11-25", "2026-11-23", "2026-11-06"]
    assert sum(len(ws.writes) for ws in sheet.worksheets()) == writes_before


def test_a_learned_name_fills_the_category_when_auto_sort_has_none():
    install()
    get_database_manager().learn_budget_alias("maryann", "Restaurant")

    res = analyze(SwileCapture(is_swile=True, lignes=[line("Maryann", "Hier, 12:52", -6.9)]))

    assert by_merchant(res.json())["Maryann"]["categorie"] == "Restaurant"


def test_ambiguous_auto_sort_or_a_group_never_prefills():
    install(BudgetSheetState(
        groups=STATE.groups, categories=STATE.categories,
        auto_sort=(("carrefour", "Course"), ("carrefour", "Chats"), ("fnac", "Loisir")),
    ))

    res = analyze(SwileCapture(is_swile=True, lignes=[
        line("Carrefour", "Hier, 10:00", -4.7), line("Fnac", "Hier, 11:00", -20.0),
    ]))

    lines = by_merchant(res.json())
    assert lines["Carrefour"]["categorie"] is None and lines["Fnac"]["categorie"] is None


def test_same_amount_within_three_days_is_a_duplicate_shown_unchecked():
    install(BudgetSheetState(
        groups=STATE.groups, categories=STATE.categories, auto_sort=STATE.auto_sort,
        swile=((date(2026, 11, 22), 25.0, "Course", "Otis : courses"), (date(2026, 11, 10), 24.0, "Restaurant", "")),
        income=((date(2026, 11, 6), 242.0, "Ticket resto"),),
    ))

    res = analyze(SwileCapture(is_swile=True, lignes=[
        line("Intermarche", "samedi 21 nov. 2026, 10:27", -25.0),
        line("Intermarche", "samedi 14 nov. 2026, 11:10", -25.0),  # 8 jours d'écart : pas un doublon
        line("Sas Thimonet", "mardi 10 nov. 2026, 08:19", -24.0),
        line("Crédit titres-resto", "vendredi 6 nov. 2026, 04:13", 242.0),
    ]))

    lines = res.json()["lignes"]
    assert [(l["date"], l["cochee"], l["doublon"]) for l in lines] == [
        ("2026-11-21", False, "déjà saisie le 22/11 (Course) ?"),
        ("2026-11-14", True, None),
        ("2026-11-10", False, "déjà saisie le 10/11 (Restaurant) ?"),
        ("2026-11-06", False, "déjà saisie le 06/11 (Ticket resto) ?"),
    ]


def test_one_recorded_line_answers_for_a_single_captured_line():
    install(BudgetSheetState(
        groups=STATE.groups, categories=STATE.categories, auto_sort=STATE.auto_sort,
        swile=((date(2026, 11, 21), 25.0, "Course", ""),),
    ))

    res = analyze(SwileCapture(is_swile=True, lignes=[
        line("Intermarche", "samedi 21 nov. 2026, 10:27", -25.0),
        line("Intermarche", "samedi 21 nov. 2026, 18:00", -25.0),  # 2e achat du jour, sur la même capture
    ]))

    assert [l["cochee"] for l in res.json()["lignes"]] == [False, True]


def test_identical_lines_of_several_captures_are_merged():
    install()
    home = SwileCapture(is_swile=True, solde=95.64, lignes=[
        line("Intermarche", "Hier, 17:35", -12.81), line("Maryann", "lundi, 12:52", -6.9),
    ])
    history = SwileCapture(is_swile=True, lignes=[
        line("Intermarche", "mercredi 25 nov. 2026, 17:35", -12.81),
        line("Maryann", "lundi 23 nov. 2026, 12:52", -6.9),
        line("Burger King", "vendredi 13 nov. 2026, 12:44", -30.7),
    ])

    res = analyze(home, history)

    assert [(l["marchand"], l["date"]) for l in res.json()["lignes"]] == [
        ("Intermarche", "2026-11-25"), ("Maryann", "2026-11-23"), ("Burger King", "2026-11-13"),
    ]


def test_unreadable_lines_and_foreign_images_are_ignored_and_reported():
    install()

    res = analyze(
        SwileCapture(is_swile=True, lignes=[line("Intermarche", "jeudi 29", -25.0), line("Fnac", "Hier", 0.0),
                                            line("Carrefour", "Hier, 12:16", -4.7)]),
        SwileCapture(is_swile=False, message="Capture d'un ticket de caisse."),
    )

    body = res.json()
    assert [l["marchand"] for l in body["lignes"]] == ["Carrefour"]
    assert body["avertissements"] == [
        "Ligne illisible ignorée : Intermarche (« jeudi 29 », -25,00 €).",
        "Ligne illisible ignorée : Fnac (« Hier », 0,00 €).",
        "Capture 2 ignorée : Capture d'un ticket de caisse.",
    ]


RESTE_SWILE_ROW = 8  # ligne 9 de Gestion (index 0)
NOVEMBER_PLANNED_COL = 5 + 3 * 2  # F + un bloc de 3 colonnes par mois (septembre, octobre, novembre)


def set_reste_swile(sheet, value):
    row = sheet.worksheet("Gestion").rows[RESTE_SWILE_ROW]
    assert row[0] == "Reste Swile"
    row.extend([""] * (NOVEMBER_PLANNED_COL + 1 - len(row)))
    row[NOVEMBER_PLANNED_COL] = value


def test_balance_is_shown_with_the_current_value_of_the_active_month():
    sheet = install()

    empty = analyze(SwileCapture(is_swile=True, solde=95.64, lignes=[]))
    set_reste_swile(sheet, 80.0)
    sheet_connector_cache_reset()
    filled = analyze(SwileCapture(is_swile=True, solde=95.64, lignes=[]))

    assert empty.status_code == 200, empty.text
    assert empty.json()["solde"] == {"nouveau": 95.64, "actuel": None, "mois": "novembre 2026"}
    assert filled.json()["solde"] == {"nouveau": 95.64, "actuel": 80.0, "mois": "novembre 2026"}


def reste_swile_value(sheet):
    row = sheet.worksheet("Gestion").rows[RESTE_SWILE_ROW]
    return row[NOVEMBER_PLANNED_COL] if len(row) > NOVEMBER_PLANNED_COL else ""


def sheet_connector_cache_reset():
    from app.core.dependencies import get_budget_connector
    get_budget_connector().invalidate_cache()


def test_missing_reste_swile_line_is_an_explicit_error():
    sheet = install()
    sheet.worksheet("Gestion").rows[RESTE_SWILE_ROW][0] = "Reste Swyle"

    res = analyze(SwileCapture(is_swile=True, solde=95.64, lignes=[]))

    assert res.status_code == 502
    assert "Reste Swile" in res.json()["detail"] and "Reste Swyle" in res.json()["detail"]


def test_nothing_readable_is_refused_with_the_reasons():
    install()

    res = analyze(SwileCapture(is_swile=False, message="Photo de chat."))

    assert res.status_code == 422
    assert "Capture 1 ignorée : Photo de chat." in res.json()["detail"]


def test_vision_outage_is_a_503():
    install()
    with patch(ANALYZE, side_effect=VisionServiceUnavailableError("Tous les modèles Gemini Vision ont échoué : x (429)")):
        res = client.post("/api/v1/budget/swile/analyze", files=[("files", ("a.jpg", BytesIO(b"img"), "image/jpeg"))])

    assert res.status_code == 503 and "x (429)" in res.json()["detail"]


def test_empty_file_is_refused():
    install()
    res = client.post("/api/v1/budget/swile/analyze", files=[("files", ("a.jpg", BytesIO(b""), "image/jpeg"))])
    assert res.status_code == 400
