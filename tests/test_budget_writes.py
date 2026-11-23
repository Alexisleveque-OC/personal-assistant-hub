"""Phase 10, étape 3 : écritures du connecteur Budget (faux classeur, aucun appel à Google)."""
from datetime import date

import pytest

from app.connectors.sheets.budget_connector import (
    BudgetConnector,
    BudgetEntryChangedError,
    BudgetHeaderError,
)
from app.connectors.sheets.budget_models import BudgetEntry
from tests.budget_fakes import BudgetSheetState, build_budget_spreadsheet, serial

TODAY = date(2026, 11, 23)
OLD = date(2026, 11, 2)


def setup(state: BudgetSheetState = None):
    spreadsheet = build_budget_spreadsheet(state or BudgetSheetState(
        debits=((OLD, 12.0, "Course", "", "CB LECLERC"),),
        swile=((OLD, 9.5, "Restaurant", "midi"),),
    ))
    return BudgetConnector(spreadsheet, today=lambda: TODAY), spreadsheet


def entry(sheet: str = "Débit", amount: float = 23.5, category: str = "Course", label: str = "Otis : pizza") -> BudgetEntry:
    return BudgetEntry(sheet=sheet, day=TODAY, amount=amount, category=category, label=label)


# --- Ajout -----------------------------------------------------------------------------------------

def test_expense_is_written_on_the_first_empty_row_with_label_in_column_e() -> None:
    connector, sheet = setup()
    row = connector.add_entry(entry())
    debit = sheet.worksheet("Débit")
    assert row == 3
    assert debit.writes == [("A3:E3", [["2026-11-23", 23.5, "Course", "", "Otis : pizza"]])]
    assert debit.rows[2] == [serial(TODAY), 23.5, "Course", "", "Otis : pizza"]


def test_swile_has_no_label_column_so_the_label_goes_in_comments() -> None:
    connector, sheet = setup()
    connector.add_entry(entry(sheet="Swile", category="Restaurant"))
    assert sheet.worksheet("Swile").writes == [("A3:D3", [["2026-11-23", 23.5, "Restaurant", "Otis : pizza"]])]


def test_income_goes_to_revenus_and_grows_a_full_grid_first() -> None:
    connector, sheet = setup(BudgetSheetState(income=((OLD, 300.0, "CAF"),), spare_rows=0))
    revenus = sheet.worksheet("Revenus")
    assert revenus.row_count == 2
    row = connector.add_entry(entry(sheet="Revenus", amount=150.0, category="CAF", label="Otis : prime"))
    assert row == 3 and revenus.row_count >= 3
    assert revenus.rows[2] == [serial(TODAY), 150.0, "CAF", "", "Otis : prime"]


def test_refund_is_a_negative_amount() -> None:
    connector, sheet = setup()
    connector.add_entry(entry(amount=-20.0))
    assert sheet.worksheet("Débit").rows[2][1] == -20.0


def test_write_rereads_the_sheet_so_rows_added_meanwhile_are_never_overwritten() -> None:
    connector, sheet = setup()
    connector.add_entry(entry())  # met « Débit » en cache…
    sheet.worksheet("Débit").rows.append([serial(TODAY), 5.0, "Chats", "", "CB ANIMALERIE"])  # …import entre-temps
    assert connector.add_entry(entry(label="Otis : glace")) == 5


def test_write_invalidates_the_sheet_and_gestion_caches() -> None:
    connector, sheet = setup(BudgetSheetState(income=((OLD, 300.0, "CAF"),)))
    connector.get_remaining("Course")
    connector.get_income("CAF", connector.get_active_month())
    gestion_reads = sheet.worksheet("Gestion").reads
    connector.add_entry(entry(sheet="Revenus", amount=150.0, category="CAF"))
    assert connector.get_income("CAF", connector.get_active_month()).total == 450.0
    connector.get_remaining("Course")
    assert sheet.worksheet("Gestion").reads == gestion_reads + 1


def test_unexpected_headers_block_the_write() -> None:
    connector, sheet = setup()
    sheet.worksheet("Débit").rows[0] = ["Jour", "Montant", "Type", "Commentaires", ""]
    with pytest.raises(BudgetHeaderError, match="Débit"):
        connector.add_entry(entry())
    assert sheet.worksheet("Débit").writes == []


# --- Retrouver par contenu, supprimer, changer la catégorie ----------------------------------------

def test_delete_finds_the_row_by_content_even_after_rows_were_inserted_above() -> None:
    connector, sheet = setup()
    written = entry()
    connector.add_entry(written)
    debit = sheet.worksheet("Débit")
    debit.rows.insert(1, [serial(OLD), 3.0, "Chats", "", "CB TRI"])
    connector.delete_entry(written)
    assert all(row[4] != "Otis : pizza" for row in debit.rows)
    assert len(debit.rows) == 3


def test_delete_refuses_a_row_modified_since() -> None:
    connector, sheet = setup()
    written = entry()
    connector.add_entry(written)
    sheet.worksheet("Débit").rows[2][1] = 25.0
    with pytest.raises(BudgetEntryChangedError, match="modifiée depuis"):
        connector.delete_entry(written)
    assert len(sheet.worksheet("Débit").rows) == 3


def test_delete_refuses_a_row_with_a_comment_added_since() -> None:
    connector, sheet = setup()
    written = entry()
    connector.add_entry(written)
    sheet.worksheet("Débit").rows[2][3] = "partagé avec Candice"
    with pytest.raises(BudgetEntryChangedError):
        connector.delete_entry(written)


def test_delete_removes_only_one_of_two_identical_rows() -> None:
    connector, sheet = setup()
    written = entry()
    connector.add_entry(written)
    connector.add_entry(written)
    connector.delete_entry(written)
    assert [row[4] for row in sheet.worksheet("Débit").rows].count("Otis : pizza") == 1


def test_trailing_space_in_a_category_name_does_not_make_the_row_look_modified() -> None:
    connector, sheet = setup()
    written = entry(category="Cadeaux Elias ")
    connector.add_entry(written)
    sheet.worksheet("Débit").rows[2][2] = "Cadeaux Elias"  # Sheets peut rogner l'espace final
    connector.delete_entry(written)
    assert len(sheet.worksheet("Débit").rows) == 2


def test_change_category_of_an_unchanged_row() -> None:
    connector, sheet = setup()
    written = entry()
    connector.add_entry(written)
    sheet.worksheet("Débit").rows.insert(1, [serial(OLD), 3.0, "Chats", "", "CB TRI"])
    changed = connector.set_entry_category(written, "Restaurant")
    assert changed == written.model_copy(update={"category": "Restaurant"})
    assert sheet.worksheet("Débit").rows[3][2] == "Restaurant"
    assert sheet.worksheet("Débit").writes[-1] == ("C4", [["Restaurant"]])


def test_change_category_refuses_a_row_deleted_since() -> None:
    connector, sheet = setup()
    written = entry()
    connector.add_entry(written)
    del sheet.worksheet("Débit").rows[2]
    with pytest.raises(BudgetEntryChangedError, match="supprimée ou modifiée depuis"):
        connector.set_entry_category(written, "Restaurant")


# --- Groupes et résolution restreinte --------------------------------------------------------------

def test_group_members_of_a_group_and_of_a_plain_category() -> None:
    connector, _ = setup()
    assert connector.group_members("loisir") == ["Loisir Alex", "Cadeaux Elias "]
    assert connector.group_members("Course") == []
    assert connector.group_members("Epargne") == []  # la catégorie homonyme l'emporte


def test_resolution_restricted_to_income_categories() -> None:
    connector, _ = setup()
    income = connector.group_members("Revenus")
    assert connector.resolve_category("caf", among=income).category == "CAF"
    assert connector.resolve_category("course", among=income).status == "unknown"
    assert connector.resolve_category("salaire", among=income).category == "Salaire Alexis"
