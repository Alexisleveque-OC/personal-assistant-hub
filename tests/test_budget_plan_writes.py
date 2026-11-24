"""Phase 10, étape 4 : écritures du connecteur Budget dans `Échéanciers` et `Dépenses Multiples` (faux classeur).

Format exact des formulaires de l'Apps Script (`createInstallment` / `createSplitTransaction`), relevé le 24/11.
"""
from datetime import date

import pytest

from app.connectors.sheets.budget_connector import BudgetConnector, BudgetEntryChangedError, BudgetHeaderError
from app.connectors.sheets.budget_models import BudgetMonth, NewInstallment, SplitExpense, SplitPart
from tests.budget_fakes import BudgetSheetState, Installment, build_budget_spreadsheet, serial

TODAY = date(2026, 11, 24)
CURRENCY = {"numberFormat": {"type": "CURRENCY", "pattern": "#,##0.00 €"}}


def setup(state: BudgetSheetState = None):
    spreadsheet = build_budget_spreadsheet(state or BudgetSheetState(
        installments=(Installment("paypal", 118.0, 4, 2, 29.5, date(2026, 9, 1), "Chats"),),
    ))
    return BudgetConnector(spreadsheet, today=lambda: TODAY), spreadsheet


def ikea(**changes) -> NewInstallment:
    values = dict(
        name="ikea", total_amount=402.95, count=4, start_month=BudgetMonth(year=2026, month=11),
        category="Course", comment="meubles",
    )
    return NewInstallment(**{**values, **changes})


def amazon(**changes) -> SplitExpense:
    values = dict(
        day=TODAY, keyword="amazon", total_amount=62.02,
        parts=(SplitPart(category="Cadeaux Elias ", amount=33.14), SplitPart(category="Course", amount=20),
               SplitPart(category="Chats", amount=8.88)),
    )
    return SplitExpense(**{**values, **changes})


# --- Modèles ---------------------------------------------------------------------------------------

def test_monthly_amount_is_rounded_half_up_to_the_cent_like_the_apps_script() -> None:
    assert ikea().monthly_amount == 100.74  # 100,7375
    assert ikea(total_amount=140.38).monthly_amount == 35.1  # 35,095 (valeur du vrai classeur)
    assert ikea(total_amount=100, count=3).monthly_amount == 33.33


def test_split_parts_must_add_up_to_the_total() -> None:
    with pytest.raises(ValueError, match="62.02.*60"):
        amazon(parts=(SplitPart(category="Course", amount=40), SplitPart(category="Chats", amount=20)))
    with pytest.raises(ValueError):
        amazon(parts=())
    with pytest.raises(ValueError):
        SplitPart(category="Course", amount=0)


def test_split_description_and_json_match_the_apps_script_format() -> None:
    split = amazon()
    assert split.description == "Cadeaux Elias  : 33.14 € | Course : 20.00 € | Chats : 8.88 €"
    assert split.parts_json == (
        '[{"category":"Cadeaux Elias ","amount":33.14},{"category":"Course","amount":20},'
        '{"category":"Chats","amount":8.88}]'
    )


# --- Échéanciers -----------------------------------------------------------------------------------

def test_installment_row_has_the_apps_script_format_and_formats() -> None:
    connector, sheet = setup()
    row = connector.add_installment(ikea())
    ws = sheet.worksheet("Échéanciers")
    assert row == 3
    assert ws.writes == [("A3:I3", [["ikea", 402.95, 4, 0, 100.74, "2026-11-01", "Course", "meubles", "Actif"]])]
    assert ws.rows[2][5] == serial(date(2026, 11, 1))  # Mois Début stocké en date, comme l'appendRow de l'Apps Script
    assert ws.formats == [
        {"range": "B3", "format": CURRENCY},
        {"range": "E3", "format": CURRENCY},
        {"range": "F3", "format": {"numberFormat": {"type": "DATE", "pattern": "mmmm yyyy"}}},
    ]


def test_installment_written_is_read_back_as_an_active_installment() -> None:
    connector, _ = setup()
    connector.get_installments()  # met l'onglet en cache
    connector.add_installment(ikea())
    written = [i for i in connector.get_installments() if i.name == "ikea"]
    assert len(written) == 1
    assert (written[0].monthly_amount, written[0].current_installment, written[0].start_month.label, written[0].status) == (
        100.74, 0, "novembre 2026", "Actif")


def test_full_installment_grid_is_grown_first() -> None:
    connector, sheet = setup(BudgetSheetState(
        installments=(Installment("paypal", 118.0, 4, 2, 29.5, date(2026, 9, 1), "Chats"),), spare_rows=0,
    ))
    assert connector.add_installment(ikea()) == 3
    assert sheet.worksheet("Échéanciers").row_count >= 3


def test_installment_undo_deletes_the_row_found_by_content() -> None:
    connector, sheet = setup()
    connector.add_installment(ikea())
    ws = sheet.worksheet("Échéanciers")
    ws.rows.insert(1, ["but", 424.99, 4, 1, 106.25, serial(date(2026, 10, 1)), "Course", "", "Actif"])
    connector.delete_entry(ikea())
    assert [r[0] for r in ws.rows[1:]] == ["but", "paypal"]


def test_installment_already_matched_by_the_import_is_not_deleted() -> None:
    connector, sheet = setup()
    connector.add_installment(ikea())
    sheet.worksheet("Échéanciers").rows[2][3] = 1  # l'import a rapproché la 1re échéance
    with pytest.raises(BudgetEntryChangedError, match="ikea.*modifié"):
        connector.delete_entry(ikea())


# --- Dépenses multiples ----------------------------------------------------------------------------

def test_split_row_has_the_apps_script_format_and_formats() -> None:
    connector, sheet = setup()
    row = connector.add_split_expense(amazon(keyword="  amazon  "))
    ws = sheet.worksheet("Dépenses Multiples")
    assert row == 2
    assert ws.writes == [("A2:F2", [[
        "2026-11-24", "amazon", 62.02, "A traiter", amazon().description, amazon().parts_json,
    ]])]
    assert ws.rows[1][0] == serial(TODAY)
    assert ws.formats == [
        {"range": "A2", "format": {"numberFormat": {"type": "DATE", "pattern": "dd/mm/yyyy"}}},
        {"range": "C2", "format": CURRENCY},
    ]


def test_split_undo_deletes_only_a_split_still_to_process() -> None:
    connector, sheet = setup()
    connector.add_split_expense(amazon())
    connector.add_split_expense(amazon(keyword="leclerc"))
    ws = sheet.worksheet("Dépenses Multiples")
    ws.rows[1][3] = "Traité"  # l'import a déjà découpé la dépense
    with pytest.raises(BudgetEntryChangedError, match="amazon.*modifié"):
        connector.delete_entry(amazon())
    connector.delete_entry(amazon(keyword="leclerc"))
    assert [r[1] for r in ws.rows[1:]] == ["amazon"]


def test_unexpected_split_headers_block_the_write() -> None:
    connector, sheet = setup()
    sheet.worksheet("Dépenses Multiples").rows[0][5] = "Parts"
    with pytest.raises(BudgetHeaderError, match="Dépenses Multiples"):
        connector.add_split_expense(amazon())
    assert sheet.worksheet("Dépenses Multiples").writes == []
