"""Phase 10, étape 5 bis : noms de catégorie appris (« loisir alexis » → Loisir Alex).

Décisions utilisateur du 24/11 : stockage dans la base de l'app ; apprentissage seulement par la réponse à la
question « lequel ? » (jamais par « non, c'était dans X ») ; annonce en une phrase ; « oublie … » ; « annule »
efface aussi l'apprentissage ; toutes les saisies et lectures ; un nom exact du classeur l'emporte toujours.
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.connectors.sheets.budget_connector import BudgetConnector
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.factory import set_agent_llm
from app.core.agent.tools.budget_models import (
    AddExpenseArgs,
    AddIncomeArgs,
    AddInstallmentArgs,
    BudgetAliasLearnedUndo,
    CorrectBudgetCategoryArgs,
    ForgetBudgetAliasArgs,
    GetBudgetRemainingArgs,
    GetIncomeArgs,
    PredeclareSplitExpenseArgs,
)
from app.core.agent.tools.budget_pending import PendingCategoryQuestions
from app.core.agent.tools.budget_tools import BudgetTools
from app.core.agent.tools.tool_error import ToolError
from app.core.agent.undo import UndoJournal, UndoService
from app.core.dependencies import set_budget_connector, set_sport_connector
from app.core.home.recent_actions import action_label
from app.core.session_manager import get_session_manager
from app.main import app
from tests.agent_fakes import ScriptedLLM, call_turn, text_turn
from tests.budget_fakes import DEFAULT_GROUPS, BudgetSheetState, GestionLine, build_budget_spreadsheet

TODAY = date(2026, 11, 24)
GROUPS = tuple(
    (name, tuple(lines) + ((GestionLine("Loisir Elias", 70.0, {(2026, 11): 10.0}),) if name == "Loisir" else ()))
    for name, lines in DEFAULT_GROUPS
)
CATEGORIES = tuple((line.name, date(2024, 1, 1), None) for _, lines in GROUPS for line in lines) + tuple(
    (group, date(2024, 1, 1), None) for group, _ in GROUPS
)


def state() -> BudgetSheetState:
    return BudgetSheetState(groups=GROUPS, categories=CATEGORIES)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def db(isolate_sqlite_database):
    return isolate_sqlite_database


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def pending(clock):
    return PendingCategoryQuestions(monotonic=clock)


def make_tools(db, pending, session_id="s1", sheet_state=None):
    spreadsheet = build_budget_spreadsheet(sheet_state or state())
    connector = BudgetConnector(spreadsheet, today=lambda: TODAY)
    tools = BudgetTools(connector, today=lambda: TODAY, aliases=db, session_id=session_id, pending=pending)
    return tools, spreadsheet


def ask_ambiguous(tools, spoken="loisir alexis"):
    with pytest.raises(ToolError, match="Loisir Alex, Loisir Elias"):
        tools.add_expense(AddExpenseArgs(montant=12, categorie=spoken, libelle="ciné"))


# --- Stockage --------------------------------------------------------------------------------------

def test_alias_store_learns_overwrites_and_forgets(db) -> None:
    assert db.get_budget_alias("loisir alexis") is None
    db.learn_budget_alias("loisir alexis", "Loisir Elias")
    db.learn_budget_alias("loisir alexis", "Loisir Alex")
    assert db.get_budget_alias("loisir alexis") == "Loisir Alex"
    assert db.list_budget_aliases() == {"loisir alexis": "Loisir Alex"}
    assert db.forget_budget_alias("loisir alexis") is True
    assert db.forget_budget_alias("loisir alexis") is False
    assert db.list_budget_aliases() == {}


# --- Question en attente ---------------------------------------------------------------------------

def test_pending_question_is_answered_only_by_a_proposed_category(pending) -> None:
    pending.ask("s1", "loisir alexis", ["Loisir Alex", "Loisir Elias"])
    assert pending.take("s2", ["Loisir Alex"]) is None
    assert pending.take("s1", ["Course", "Loisir Alex"]) == ("loisir alexis", "Loisir Alex")
    assert pending.take("s1", ["Loisir Alex"]) is None  # consommée


def test_another_answer_consumes_the_question(pending) -> None:
    pending.ask("s1", "loisir alexis", ["Loisir Alex", "Loisir Elias"])
    assert pending.take("s1", ["Course"]) is None
    assert pending.take("s1", ["Loisir Alex"]) is None


def test_two_proposed_categories_in_one_answer_teach_nothing(pending) -> None:
    pending.ask("s1", "loisir alexis", ["Loisir Alex", "Loisir Elias"])
    assert pending.take("s1", ["Loisir Alex", "Loisir Elias"]) is None


def test_pending_question_expires_after_ten_minutes(pending, clock) -> None:
    pending.ask("s1", "loisir alexis", ["Loisir Alex", "Loisir Elias"])
    clock.now += 601
    assert pending.take("s1", ["Loisir Alex"]) is None


# --- Apprentissage par la réponse à « lequel ? » ---------------------------------------------------

def test_answer_to_the_question_is_learned_announced_and_undoable(db, pending) -> None:
    tools, _ = make_tools(db, pending)
    ask_ambiguous(tools)

    result = tools.add_expense(AddExpenseArgs(montant=12, categorie="loisir alex", libelle="ciné"))

    assert db.get_budget_alias("loisir alexis") == "Loisir Alex"
    assert "loisir alexis" in result.nom_appris and "Loisir Alex" in result.nom_appris
    assert BudgetAliasLearnedUndo(alias="loisir alexis", category="Loisir Alex") in result.undos


def test_learned_name_is_used_without_question_next_time(db, pending) -> None:
    tools, sheet = make_tools(db, pending)
    db.learn_budget_alias("loisir alexis", "Loisir Alex")

    result = tools.add_expense(AddExpenseArgs(montant=9, categorie="Loisir Alexis", libelle="bowling"))

    assert sheet.worksheet("Débit").rows[1][2] == "Loisir Alex"
    assert result.ligne.rapprochement == "appris"
    assert result.nom_appris is None


def test_no_learning_when_the_answer_is_not_a_proposed_category(db, pending) -> None:
    tools, _ = make_tools(db, pending)
    ask_ambiguous(tools)
    tools.add_expense(AddExpenseArgs(montant=12, categorie="course", libelle="ciné"))
    assert db.list_budget_aliases() == {}


def test_no_learning_from_another_conversation(db, pending) -> None:
    asking, _ = make_tools(db, pending, session_id="s1")
    ask_ambiguous(asking)
    other, _ = make_tools(db, pending, session_id="s2")
    other.add_expense(AddExpenseArgs(montant=12, categorie="loisir alex", libelle="ciné"))
    assert db.list_budget_aliases() == {}


def test_correction_never_teaches(db, pending) -> None:
    """« Non, c'était dans X » : souvent une erreur de l'utilisateur, rien n'est appris (décision du 24/11)."""
    tools, _ = make_tools(db, pending)
    written = tools.add_expense(AddExpenseArgs(montant=12, categorie="course", libelle="ciné")).undos[0].entry
    ask_ambiguous(tools)
    tools.correct_category(CorrectBudgetCategoryArgs(categorie="loisir alex"), written)
    assert db.list_budget_aliases() == {}


def test_reading_the_remaining_learns_and_uses_the_name(db, pending) -> None:
    tools, _ = make_tools(db, pending)
    with pytest.raises(ToolError, match="Loisir Alex, Loisir Elias"):
        tools.get_budget_remaining(GetBudgetRemainingArgs(categorie="loisir alexis"))
    answered = tools.get_budget_remaining(GetBudgetRemainingArgs(categorie="loisir alex"))
    assert "loisir alexis" in answered.nom_appris

    again = tools.get_budget_remaining(GetBudgetRemainingArgs(categorie="loisir alexis"))
    assert (again.categorie, again.rapprochement, again.nom_appris) == ("Loisir Alex", "appris", None)


def test_income_question_answer_is_learned_and_announced(db, pending) -> None:
    tools, _ = make_tools(db, pending)
    pending.ask("s1", "allocations", ["CAF", "Salaire Alexis"])
    answered = tools.get_income(GetIncomeArgs(type="caf", mois=11, annee=2026))
    assert "allocations" in answered.nom_appris and db.get_budget_alias("allocations") == "CAF"


def test_installment_and_split_parts_learn_and_use_the_name(db, pending) -> None:
    tools, _ = make_tools(db, pending)
    with pytest.raises(ToolError, match="Loisir Alex, Loisir Elias"):
        tools.add_installment(AddInstallmentArgs(nom="vélo", montant_total=300, nb_echeances=3, categorie="loisir alexis"))
    installment = tools.add_installment(AddInstallmentArgs(
        nom="vélo", montant_total=300, nb_echeances=3, categorie="loisir alex"))
    assert installment.nom_appris and db.get_budget_alias("loisir alexis") == "Loisir Alex"
    assert BudgetAliasLearnedUndo(alias="loisir alexis", category="Loisir Alex") in installment.undos

    split = tools.predeclare_split_expense(PredeclareSplitExpenseArgs(mot_cle="decathlon", montant_total=50, parts=[
        {"categorie": "loisir alexis", "montant": 30}, {"categorie": "course", "montant": 20}]))
    assert [(p.categorie, p.rapprochement) for p in split.depense.parts] == [("Loisir Alex", "appris"), ("Course", "exact")]


# --- Priorités et garde-fous -----------------------------------------------------------------------

def test_exact_sheet_name_beats_a_learned_name(db, pending) -> None:
    tools, sheet = make_tools(db, pending)
    db.learn_budget_alias("restaurant", "Course")
    tools.add_expense(AddExpenseArgs(montant=20, categorie="Restaurant", libelle="pizza"))
    assert sheet.worksheet("Débit").rows[1][2] == "Restaurant"


def test_learned_name_of_a_vanished_category_is_ignored(db, pending) -> None:
    tools, _ = make_tools(db, pending)
    db.learn_budget_alias("loisir alexis", "Loisir Supprimé")
    ask_ambiguous(tools)


def test_learned_name_outside_the_income_group_is_ignored_for_an_income(db, pending) -> None:
    tools, _ = make_tools(db, pending)
    db.learn_budget_alias("prime", "Course")
    with pytest.raises(ToolError, match="n'est pas un type de revenu"):
        tools.add_income(AddIncomeArgs(montant=100, type="prime", libelle="prime"))


# --- Oubli et annulation ---------------------------------------------------------------------------

def test_forget_a_learned_name(db, pending) -> None:
    tools, _ = make_tools(db, pending)
    db.learn_budget_alias("loisir alexis", "Loisir Alex")
    result = tools.forget_alias(ForgetBudgetAliasArgs(nom="Loisir Alexis"))
    assert (result.nom, result.categorie) == ("loisir alexis", "Loisir Alex")
    assert db.list_budget_aliases() == {}
    ask_ambiguous(tools)  # la question revient


def test_forget_an_unknown_name_lists_the_learned_ones(db, pending) -> None:
    tools, _ = make_tools(db, pending)
    db.learn_budget_alias("resto rapide", "Restaurant")
    with pytest.raises(ToolError, match="resto rapide"):
        tools.forget_alias(ForgetBudgetAliasArgs(nom="loisir alexis"))


def test_undo_right_after_removes_the_line_and_the_learned_name(db, pending) -> None:
    tools, sheet = make_tools(db, pending)
    ask_ambiguous(tools)
    result = tools.add_expense(AddExpenseArgs(montant=12, categorie="loisir alex", libelle="ciné"))
    journal = UndoJournal(db)
    journal.record("s1", result.undos)
    service = UndoService(sport_tools=None, db=db, journal=journal, budget_tools=tools)

    outcome = service.undo_last("s1")

    assert sheet.worksheet("Débit").rows[1:] == []
    assert db.list_budget_aliases() == {}
    assert any("loisir alexis" in line for line in outcome.restored)


def test_forget_has_a_recent_action_label() -> None:
    log = {"intent": "agent", "parameters": {"tool_calls": [
        {"name": "forget_budget_alias", "args": {"nom": "loisir alexis"}}]}}
    assert action_label(log) == "Nom de catégorie oublié : loisir alexis"


# --- Câblage /interact -----------------------------------------------------------------------------

@pytest.fixture
def agent_with_budget(isolate_sqlite_database, monkeypatch):
    monkeypatch.setattr(settings, "nlu_mode", "agent")
    set_sport_connector(SqlSportConnector(db_manager=isolate_sqlite_database))
    spreadsheet = build_budget_spreadsheet(state())
    set_budget_connector(BudgetConnector(spreadsheet))
    yield spreadsheet, isolate_sqlite_database
    get_session_manager().clear_all()
    set_sport_connector(None)
    set_agent_llm(None)


def test_question_then_answer_through_interact_is_learned_and_reused(agent_with_budget) -> None:
    spreadsheet, db = agent_with_budget
    llm = ScriptedLLM([
        call_turn({"name": "add_expense", "args": {"montant": 12, "categorie": "loisir alexis", "libelle": "ciné"}}),
        text_turn("Loisir Alex ou Loisir Elias ?"),
        call_turn({"name": "add_expense", "args": {"montant": 12, "categorie": "loisir alex", "libelle": "ciné"}}),
        text_turn("C'est noté. Je retiendrai que loisir alexis, c'est Loisir Alex."),
        call_turn({"name": "add_expense", "args": {"montant": 5, "categorie": "loisir alexis", "libelle": "glace"}}),
        text_turn("5 euros en Loisir Alex."),
        call_turn({"name": "forget_budget_alias", "args": {"nom": "loisir alexis"}}),
        text_turn("J'ai oublié."),
    ])
    set_agent_llm(llm)
    client = TestClient(app)

    def ask(query):
        resp = client.post("/api/v1/interact", json={"query": query, "session_id": "aliases"})
        assert resp.status_code == 200, resp.text

    ask("J'ai dépensé 12 euros en loisir Alexis pour le ciné")
    ask("Loisir Alex")
    assert db.get_budget_alias("loisir alexis") == "Loisir Alex"
    ask("5 euros de glace en loisir Alexis")
    assert [row[2] for row in spreadsheet.worksheet("Débit").rows[1:]] == ["Loisir Alex", "Loisir Alex"]
    assert "forget_budget_alias" in {t["name"] for t in llm.requests[0]["tools"]}
    ask("Oublie loisir Alexis")
    assert db.list_budget_aliases() == {}
