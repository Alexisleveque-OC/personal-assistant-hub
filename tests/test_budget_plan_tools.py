"""Phase 10, étape 4 : outils add_installment / predeclare_split_expense, annulation, libellés et consigne."""
from datetime import date

import pytest

from app.connectors.sheets.budget_connector import BudgetConnector
from app.connectors.sheets.budget_models import BudgetEntry, BudgetMonth, NewInstallment
from app.core.agent.prompt import build_system_prompt
from app.core.agent.tools.budget_models import (
    AddInstallmentArgs,
    BudgetEntryAddedUndo,
    InstallmentAddedUndo,
    PredeclareSplitExpenseArgs,
    SplitDeclaredUndo,
)
from app.core.agent.tools.budget_registry import budget_tool_definitions
from app.core.agent.tools.budget_tools import BudgetTools
from app.core.agent.tools.tool_error import ToolError
from app.core.agent.undo import UndoBatch, UndoError, UndoJournal, UndoService, last_budget_entry
from app.core.database import get_database_manager
from app.core.home.recent_actions import action_label
from tests.budget_fakes import BudgetSheetState, build_budget_spreadsheet, serial

TODAY = date(2026, 11, 24)


def setup(state: BudgetSheetState = None):
    spreadsheet = build_budget_spreadsheet(state or BudgetSheetState())
    return BudgetTools(BudgetConnector(spreadsheet, today=lambda: TODAY), today=lambda: TODAY), spreadsheet


def installment_rows(spreadsheet):
    return spreadsheet.worksheet("Échéanciers").rows[1:]


def split_rows(spreadsheet):
    return spreadsheet.worksheet("Dépenses Multiples").rows[1:]


def split_args(**changes) -> PredeclareSplitExpenseArgs:
    values = dict(mot_cle="amazon", montant_total=62.02, parts=[
        {"categorie": "cadeau elias", "montant": 33.14}, {"categorie": "carrefour", "montant": 28.88},
    ])
    return PredeclareSplitExpenseArgs(**{**values, **changes})


# --- add_installment -------------------------------------------------------------------------------

def test_installment_starts_this_month_by_default() -> None:
    tools, sheet = setup()
    result = tools.add_installment(AddInstallmentArgs(
        nom="ikea", montant_total=402.95, nb_echeances=4, categorie="course", commentaire="meubles"))
    assert installment_rows(sheet) == [
        ["ikea", 402.95, 4, 0, 100.74, serial(date(2026, 11, 1)), "Course", "meubles", "Actif"]]
    assert result.action == "echeancier_ajoute"
    assert (result.echeancier.mensualite, result.echeancier.mois_debut, result.echeancier.echeances_restantes) == (
        100.74, "novembre 2026", 4)
    assert result.undos == [InstallmentAddedUndo(installment=NewInstallment(
        name="ikea", total_amount=402.95, count=4, start_month=BudgetMonth(year=2026, month=11), category="Course",
        comment="meubles"))]


@pytest.mark.parametrize("mois, annee, expected", [
    (12, None, "décembre 2026"),
    (1, None, "janvier 2027"),  # mois déjà passé cette année → l'an prochain
    (10, 2026, "octobre 2026"),
])
def test_installment_start_month_when_said(mois, annee, expected) -> None:
    tools, _ = setup()
    result = tools.add_installment(AddInstallmentArgs(
        nom="but", montant_total=400, nb_echeances=4, categorie="course", mois_debut=mois, annee_debut=annee))
    assert result.echeancier.mois_debut == expected


def test_installment_on_a_group_or_ambiguous_category_writes_nothing() -> None:
    tools, sheet = setup()
    with pytest.raises(ToolError, match="Loisir Alex, Cadeaux Elias"):
        tools.add_installment(AddInstallmentArgs(nom="fnac", montant_total=300, nb_echeances=3, categorie="loisir"))
    with pytest.raises(ToolError, match="ambiguë"):
        tools.add_installment(AddInstallmentArgs(nom="x", montant_total=300, nb_echeances=3, categorie="amazon prime"))
    assert installment_rows(sheet) == []


def test_installment_needs_at_least_two_payments_and_a_name() -> None:
    with pytest.raises(ValueError):
        AddInstallmentArgs(nom="ikea", montant_total=400, nb_echeances=1, categorie="course")
    with pytest.raises(ValueError):
        AddInstallmentArgs(nom="  ", montant_total=400, nb_echeances=4, categorie="course")


# --- predeclare_split_expense ----------------------------------------------------------------------

def test_split_is_predeclared_with_resolved_categories() -> None:
    tools, sheet = setup()
    result = tools.predeclare_split_expense(split_args())
    assert split_rows(sheet) == [[
        serial(TODAY), "amazon", 62.02, "A traiter", "Cadeaux Elias  : 33.14 € | Course : 28.88 €",
        '[{"category":"Cadeaux Elias ","amount":33.14},{"category":"Course","amount":28.88}]',
    ]]
    assert result.action == "depense_multiple_predeclaree"
    assert [(p.categorie, p.montant, p.rapprochement) for p in result.depense.parts] == [
        ("Cadeaux Elias", 33.14, "nom_proche"), ("Course", 28.88, "tri_auto")]
    assert isinstance(result.undos[0], SplitDeclaredUndo)


def test_split_on_a_said_date() -> None:
    tools, sheet = setup()
    tools.predeclare_split_expense(split_args(date=date(2026, 11, 26)))
    assert split_rows(sheet)[0][0] == serial(date(2026, 11, 26))


def test_split_whose_parts_do_not_add_up_is_refused_without_writing() -> None:
    tools, sheet = setup()
    with pytest.raises(ToolError, match="62.02.*60"):
        tools.predeclare_split_expense(split_args(parts=[
            {"categorie": "course", "montant": 40}, {"categorie": "chats", "montant": 20}]))
    assert split_rows(sheet) == []


def test_split_with_a_group_category_asks_which_one_without_writing() -> None:
    tools, sheet = setup()
    with pytest.raises(ToolError, match="Loisir Alex, Cadeaux Elias"):
        tools.predeclare_split_expense(split_args(parts=[
            {"categorie": "loisir", "montant": 30}, {"categorie": "course", "montant": 32.02}]))
    assert split_rows(sheet) == []


def test_split_keyword_is_required() -> None:
    with pytest.raises(ValueError):
        split_args(mot_cle=" ")


# --- Annulation ------------------------------------------------------------------------------------

def undo_service(tools: BudgetTools) -> UndoService:
    db = get_database_manager()
    return UndoService(sport_tools=None, db=db, journal=UndoJournal(db), budget_tools=tools)


def test_undo_deletes_the_installment_and_the_split() -> None:
    tools, sheet = setup()
    service = undo_service(tools)
    service.journal.record("s1", tools.add_installment(AddInstallmentArgs(
        nom="ikea", montant_total=402.95, nb_echeances=4, categorie="course")).undos)
    service.journal.record("s1", tools.predeclare_split_expense(split_args()).undos)
    assert "amazon" in service.undo_last("s1").restored[0]
    assert split_rows(sheet) == []
    assert "ikea" in service.undo_last("s1").restored[0]
    assert installment_rows(sheet) == []


def test_undo_refuses_an_installment_already_matched_by_the_import() -> None:
    tools, sheet = setup()
    service = undo_service(tools)
    service.journal.record("s1", tools.add_installment(AddInstallmentArgs(
        nom="ikea", montant_total=402.95, nb_echeances=4, categorie="course")).undos)
    installment_rows(sheet)[0][3] = 1
    with pytest.raises(UndoError, match="modifié"):
        service.undo_last("s1")
    assert len(installment_rows(sheet)) == 1


def test_category_correction_ignores_installments_and_splits() -> None:
    """« Non, c'était dans X » ne vise que les dépenses et revenus (étape 3)."""
    tools, _ = setup()
    split_undo = tools.predeclare_split_expense(split_args()).undos[0]
    assert last_budget_entry(UndoBatch(id=1, undos=[split_undo])) is None
    entry = BudgetEntry(sheet="Débit", day=TODAY, amount=5, category="Course", label="Otis : a")
    assert last_budget_entry(UndoBatch(id=2, undos=[BudgetEntryAddedUndo(entry=entry), split_undo])) == entry


# --- Déclaration, libellés, consigne ---------------------------------------------------------------

def test_tools_are_declared_to_the_agent() -> None:
    tools, _ = setup()
    names = {d.name for d in budget_tool_definitions(tools)}
    assert {"add_installment", "predeclare_split_expense"} <= names


@pytest.mark.parametrize("tool, args, label", [
    ("add_installment", {"nom": "ikea", "montant_total": 402.95, "nb_echeances": 4},
     "Échéancier créé : ikea, 402,95 € en 4 fois"),
    ("predeclare_split_expense", {"mot_cle": "amazon", "montant_total": 62.02},
     "Dépense multiple pré-déclarée : amazon, 62,02 €"),
])
def test_recent_action_labels(tool, args, label) -> None:
    log = {"intent": "agent", "parameters": {"tool_calls": [{"name": tool, "args": args}]}}
    assert action_label(log) == label


def test_prompt_has_installment_and_split_rules() -> None:
    prompt = build_system_prompt(TODAY, [])
    for expected in ("add_installment", "predeclare_split_expense", "mot_cle"):
        assert expected in prompt
