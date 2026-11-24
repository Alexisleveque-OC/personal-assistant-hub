"""Phase 10, étape 3 : outils d'écriture du budget (dépense, remboursement, revenu, correction) et leur annulation."""
from datetime import date

import pytest

from app.connectors.sheets.budget_connector import BudgetConnector
from app.connectors.sheets.budget_models import BudgetEntry
from app.core.agent.tools.budget_models import (
    AddExpenseArgs,
    AddIncomeArgs,
    BudgetCategoryChangedUndo,
    BudgetEntryAddedUndo,
    CorrectBudgetCategoryArgs,
)
from app.core.agent.tools.budget_registry import budget_tool_definitions
from app.core.agent.tools.budget_tools import BudgetTools
from app.core.agent.tools.tool_error import ToolError
from app.core.agent.undo import UndoBatch, UndoError, UndoJournal, UndoService, last_budget_entry
from app.core.database import get_database_manager
from tests.budget_fakes import BudgetSheetState, build_budget_spreadsheet, serial

TODAY = date(2026, 11, 23)


def setup(state: BudgetSheetState = None):
    spreadsheet = build_budget_spreadsheet(state or BudgetSheetState())
    connector = BudgetConnector(spreadsheet, today=lambda: TODAY)
    return BudgetTools(connector, today=lambda: TODAY), spreadsheet


def debit_rows(spreadsheet):
    return spreadsheet.worksheet("Débit").rows[1:]


# --- add_expense -----------------------------------------------------------------------------------

def test_expense_written_today_in_debit_with_otis_label() -> None:
    tools, sheet = setup()
    result = tools.add_expense(AddExpenseArgs(montant=23.5, categorie="course", libelle="courses Leclerc"))
    assert debit_rows(sheet) == [[serial(TODAY), 23.5, "Course", "", "Otis : courses Leclerc"]]
    assert result.action == "depense_ajoutee"
    assert (result.ligne.onglet, result.ligne.categorie, result.ligne.montant, result.ligne.date) == (
        "Débit", "Course", 23.5, TODAY)
    assert result.undos == [BudgetEntryAddedUndo(entry=BudgetEntry(
        sheet="Débit", day=TODAY, amount=23.5, category="Course", label="Otis : courses Leclerc"))]


def test_expense_on_a_said_date() -> None:
    tools, sheet = setup()
    tools.add_expense(AddExpenseArgs(montant=8, categorie="restaurant", libelle="kebab", date=date(2026, 11, 22)))
    assert debit_rows(sheet)[0][0] == serial(date(2026, 11, 22))


def test_expense_in_swile_goes_to_the_swile_sheet() -> None:
    tools, sheet = setup()
    result = tools.add_expense(AddExpenseArgs(montant=11.9, categorie="restaurant", libelle="midi", swile=True))
    assert sheet.worksheet("Swile").rows[1:] == [[serial(TODAY), 11.9, "Restaurant", "Otis : midi"]]
    assert result.ligne.onglet == "Swile"


def test_refund_is_a_negative_debit_line() -> None:
    tools, sheet = setup()
    result = tools.add_expense(AddExpenseArgs(montant=20, categorie="chats", libelle="véto", remboursement=True))
    assert debit_rows(sheet)[0][1] == -20.0
    assert (result.action, result.ligne.montant) == ("remboursement_ajoute", -20.0)


def test_expense_on_a_group_asks_which_category_without_writing() -> None:
    tools, sheet = setup()
    with pytest.raises(ToolError, match="Loisir Alex, Cadeaux Elias") as exc:
        tools.add_expense(AddExpenseArgs(montant=15, categorie="loisir", libelle="ciné"))
    assert "Demande" in str(exc.value)
    assert debit_rows(sheet) == []


def test_expense_with_ambiguous_or_unknown_category_writes_nothing() -> None:
    tools, sheet = setup()
    with pytest.raises(ToolError, match="ambiguë"):
        tools.add_expense(AddExpenseArgs(montant=15, categorie="amazon prime", libelle="colis"))
    with pytest.raises(ToolError, match="inconnue"):
        tools.add_expense(AddExpenseArgs(montant=15, categorie="jardinage", libelle="pelle"))
    assert debit_rows(sheet) == []


def test_amount_must_be_positive_and_label_not_blank() -> None:
    with pytest.raises(ValueError):
        AddExpenseArgs(montant=0, categorie="course", libelle="x")
    with pytest.raises(ValueError):
        AddExpenseArgs(montant=-5, categorie="course", libelle="x")
    with pytest.raises(ValueError):
        AddExpenseArgs(montant=5, categorie="course", libelle="  ")


def test_amount_is_rounded_to_the_cent() -> None:
    tools, sheet = setup()
    tools.add_expense(AddExpenseArgs(montant=12.345, categorie="course", libelle="pain"))
    assert debit_rows(sheet)[0][1] == 12.35


# --- add_income ------------------------------------------------------------------------------------

def test_income_written_in_revenus_with_an_income_category() -> None:
    tools, sheet = setup()
    result = tools.add_income(AddIncomeArgs(montant=150, type="caf", libelle="prime de Noël"))
    assert sheet.worksheet("Revenus").rows[1:] == [[serial(TODAY), 150.0, "CAF", "", "Otis : prime de Noël"]]
    assert (result.action, result.ligne.onglet) == ("revenu_ajoute", "Revenus")


def test_income_refuses_a_spending_category_and_lists_income_types() -> None:
    tools, sheet = setup()
    with pytest.raises(ToolError, match="Salaire Alexis, CAF"):
        tools.add_income(AddIncomeArgs(montant=150, type="course", libelle="x"))
    assert sheet.worksheet("Revenus").rows[1:] == []


# --- correct_budget_category -----------------------------------------------------------------------

def test_correction_changes_the_category_of_the_last_otis_line() -> None:
    tools, sheet = setup()
    written = tools.add_expense(AddExpenseArgs(montant=23.5, categorie="course", libelle="pizza")).undos[0].entry
    result = tools.correct_category(CorrectBudgetCategoryArgs(categorie="restaurant"), written)
    assert debit_rows(sheet)[0][2] == "Restaurant"
    assert (result.action, result.ligne.categorie, result.ancienne_categorie) == (
        "categorie_corrigee", "Restaurant", "Course")
    assert result.undos == [BudgetCategoryChangedUndo(
        entry=written.model_copy(update={"category": "Restaurant"}), previous_category="Course")]


def test_correction_without_a_line_written_just_before_is_refused() -> None:
    tools, _ = setup()
    with pytest.raises(ToolError, match="rien à corriger"):
        tools.correct_category(CorrectBudgetCategoryArgs(categorie="restaurant"), None)


def test_correction_refuses_a_line_modified_since() -> None:
    tools, sheet = setup()
    written = tools.add_expense(AddExpenseArgs(montant=23.5, categorie="course", libelle="pizza")).undos[0].entry
    sheet.worksheet("Débit").rows[1][1] = 30.0
    with pytest.raises(ToolError, match="modifiée depuis"):
        tools.correct_category(CorrectBudgetCategoryArgs(categorie="restaurant"), written)


def test_correction_to_a_group_asks_which_category() -> None:
    tools, sheet = setup()
    written = tools.add_expense(AddExpenseArgs(montant=23.5, categorie="course", libelle="pizza")).undos[0].entry
    with pytest.raises(ToolError, match="Loisir Alex"):
        tools.correct_category(CorrectBudgetCategoryArgs(categorie="loisir"), written)
    assert debit_rows(sheet)[0][2] == "Course"


def test_correction_of_an_income_stays_among_income_categories() -> None:
    tools, sheet = setup()
    written = tools.add_income(AddIncomeArgs(montant=150, type="caf", libelle="x")).undos[0].entry
    with pytest.raises(ToolError, match="Salaire Alexis, CAF"):
        tools.correct_category(CorrectBudgetCategoryArgs(categorie="course"), written)
    tools.correct_category(CorrectBudgetCategoryArgs(categorie="salaire"), written)
    assert sheet.worksheet("Revenus").rows[1][2] == "Salaire Alexis"


def test_correction_tool_uses_the_last_entry_given_by_the_journal() -> None:
    tools, sheet = setup()
    written = tools.add_expense(AddExpenseArgs(montant=23.5, categorie="course", libelle="pizza")).undos[0].entry
    definitions = {d.name: d for d in budget_tool_definitions(tools, last_entry=lambda: written)}
    assert {"add_expense", "add_income", "correct_budget_category"} <= set(definitions)
    definitions["correct_budget_category"].handler(CorrectBudgetCategoryArgs(categorie="restaurant"))
    assert debit_rows(sheet)[0][2] == "Restaurant"


def test_last_budget_entry_reads_the_latest_budget_undo_of_the_batch() -> None:
    first = BudgetEntry(sheet="Débit", day=TODAY, amount=5, category="Course", label="Otis : a")
    after = first.model_copy(update={"category": "Chats"})
    assert last_budget_entry(None) is None
    assert last_budget_entry(UndoBatch(id=1, undos=[BudgetEntryAddedUndo(entry=first)])) == first
    batch = UndoBatch(id=2, undos=[BudgetCategoryChangedUndo(entry=after, previous_category="Course")])
    assert last_budget_entry(batch) == after


# --- Annulation ------------------------------------------------------------------------------------

def undo_service(tools: BudgetTools) -> UndoService:
    db = get_database_manager()
    return UndoService(sport_tools=None, db=db, journal=UndoJournal(db), budget_tools=tools)


def test_undo_deletes_the_written_line_found_by_content() -> None:
    tools, sheet = setup()
    service = undo_service(tools)
    result = tools.add_expense(AddExpenseArgs(montant=23.5, categorie="course", libelle="pizza"))
    service.journal.record("s1", result.undos)
    sheet.worksheet("Débit").rows.insert(1, [serial(TODAY), 3.0, "Chats", "", "CB IMPORT"])  # import entre-temps
    outcome = service.undo_last("s1")
    assert debit_rows(sheet) == [[serial(TODAY), 3.0, "Chats", "", "CB IMPORT"]]
    assert "Otis : pizza" in outcome.restored[0]


def test_undo_refuses_a_line_modified_since() -> None:
    tools, sheet = setup()
    service = undo_service(tools)
    service.journal.record("s1", tools.add_expense(AddExpenseArgs(montant=23.5, categorie="course", libelle="pizza")).undos)
    sheet.worksheet("Débit").rows[1][2] = "Restaurant"
    with pytest.raises(UndoError, match="modifiée depuis"):
        service.undo_last("s1")
    assert len(debit_rows(sheet)) == 1


def test_undo_of_a_correction_restores_the_previous_category() -> None:
    tools, sheet = setup()
    service = undo_service(tools)
    added = tools.add_expense(AddExpenseArgs(montant=23.5, categorie="course", libelle="pizza"))
    service.journal.record("s1", added.undos)
    corrected = tools.correct_category(CorrectBudgetCategoryArgs(categorie="restaurant"), added.undos[0].entry)
    service.journal.record("s1", corrected.undos)
    service.undo_last("s1")
    assert debit_rows(sheet)[0][2] == "Course"
    service.undo_last("s1")  # puis l'ajout lui-même
    assert debit_rows(sheet) == []


def test_undo_without_budget_sheet_says_so() -> None:
    tools, _ = setup()
    db = get_database_manager()
    entry = BudgetEntry(sheet="Débit", day=TODAY, amount=5, category="Course", label="Otis : a")
    service = UndoService(sport_tools=None, db=db, journal=UndoJournal(db))
    service.journal.record("s1", [BudgetEntryAddedUndo(entry=entry)])
    with pytest.raises(UndoError, match="Budget est indisponible"):
        service.undo_last("s1")
