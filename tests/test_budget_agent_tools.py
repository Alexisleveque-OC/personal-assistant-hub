"""Phase 10, étape 2 : outils de lecture du budget pour l'agent (faux classeur, aucun appel à Google)."""
from datetime import date

import pytest

from app.connectors.sheets.budget_connector import BudgetConnector
from app.core.agent.tools.budget_models import GetBudgetRemainingArgs, GetIncomeArgs, GetInstallmentsArgs
from app.core.agent.tools.budget_registry import budget_tool_definitions
from app.core.agent.tools.budget_tools import BudgetTools
from app.core.agent.tools.tool_error import ToolError
from tests.budget_fakes import BudgetSheetState, Installment, build_budget_spreadsheet

TODAY = date(2026, 11, 23)


def budget_connector(state: BudgetSheetState = None) -> BudgetConnector:
    return BudgetConnector(build_budget_spreadsheet(state or BudgetSheetState()), today=lambda: TODAY)


def tools(state: BudgetSheetState = None) -> BudgetTools:
    return BudgetTools(budget_connector(state))


# --- get_budget_remaining ------------------------------------------------------------------------

def test_remaining_gives_total_and_active_month() -> None:
    view = tools().get_budget_remaining(GetBudgetRemainingArgs(categorie="course"))
    assert (view.categorie, view.categorie_dite, view.rapprochement) == ("Course", "course", "exact")
    assert (view.reste_total, view.mois, view.reste_du_mois) == (412.5, "novembre 2026", 230.0)
    assert view.categories_du_groupe == []


def test_remaining_for_a_given_month() -> None:
    view = tools().get_budget_remaining(GetBudgetRemainingArgs(categorie="Restaurant", mois=10, annee=2026))
    assert (view.mois, view.reste_du_mois) == ("octobre 2026", -10.0)


def test_remaining_month_without_year_uses_the_active_month_year() -> None:
    view = tools().get_budget_remaining(GetBudgetRemainingArgs(categorie="Restaurant", mois=10))
    assert view.mois == "octobre 2026"


def test_remaining_through_auto_sort_or_close_name_says_which_category() -> None:
    assert tools().get_budget_remaining(GetBudgetRemainingArgs(categorie="croquettes")).rapprochement == "tri_auto"
    view = tools().get_budget_remaining(GetBudgetRemainingArgs(categorie="cadeau elias"))
    assert (view.categorie, view.rapprochement) == ("Cadeaux Elias", "nom_proche")  # espace final retiré pour l'oral


def test_remaining_of_a_group_lists_its_categories() -> None:
    view = tools().get_budget_remaining(GetBudgetRemainingArgs(categorie="Loisir"))
    assert view.categories_du_groupe == ["Loisir Alex", "Cadeaux Elias"]
    assert view.reste_total == 170.0


def test_ambiguous_category_asks_instead_of_guessing() -> None:
    with pytest.raises(ToolError, match="Chats.*Loisir Alex") as exc:
        tools().get_budget_remaining(GetBudgetRemainingArgs(categorie="amazon prime"))
    assert "Demande" in str(exc.value)


def test_unknown_category_is_reported() -> None:
    with pytest.raises(ToolError, match="piscine"):
        tools().get_budget_remaining(GetBudgetRemainingArgs(categorie="piscine"))


def test_connector_errors_are_forwarded() -> None:
    with pytest.raises(ToolError, match="janvier 2027"):
        tools().get_budget_remaining(GetBudgetRemainingArgs(categorie="Course", mois=1, annee=2027))


def test_unconfigured_budget_says_why() -> None:
    unavailable = BudgetTools(None, unavailable_reason="SPREADSHEET_BUDGET_ID n'est pas renseigné")
    with pytest.raises(ToolError, match="SPREADSHEET_BUDGET_ID"):
        unavailable.get_budget_remaining(GetBudgetRemainingArgs(categorie="Course"))


# --- get_income ----------------------------------------------------------------------------------

def income_state() -> BudgetSheetState:
    return BudgetSheetState(income=(
        (date(2026, 10, 5), 267.41, "caf"),
        (date(2026, 11, 5), 267.41, "CAF"),
        (date(2026, 11, 28), 1800.0, "Salaire Alexis"),
    ))


def test_income_of_a_type_for_a_month() -> None:
    view = tools(income_state()).get_income(GetIncomeArgs(type="caf", mois=10, annee=2026))
    assert (view.type, view.mois, view.total, view.nombre) == ("CAF", "octobre 2026", 267.41, 1)


def test_income_of_every_type() -> None:
    view = tools(income_state()).get_income(GetIncomeArgs(mois=11, annee=2026))
    assert (view.type, view.total, view.nombre) == (None, 2067.41, 2)


def test_income_type_must_be_a_known_category() -> None:
    with pytest.raises(ToolError, match="loto"):
        tools(income_state()).get_income(GetIncomeArgs(type="loto", mois=11, annee=2026))


# --- get_installments ------------------------------------------------------------------------------

def installments_state() -> BudgetSheetState:
    return BudgetSheetState(installments=(
        Installment("Portable", 308.99, 4, 4, 77.25, date(2026, 5, 1), "Dépannage", status="Terminé"),
        Installment("paypal", 140.38, 4, 3, 35.1, date(2026, 8, 1), "Chats"),
        Installment("paypal", 118.0, 4, 2, 29.5, date(2026, 9, 1), "Dépannage", comment="billet de train"),
    ))


def test_installments_lists_active_ones() -> None:
    view = tools(installments_state()).get_installments(GetInstallmentsArgs())
    assert [(i.nom, i.categorie, i.echeances_restantes, i.montant_restant) for i in view.echeanciers] == [
        ("paypal", "Chats", 1, 35.1), ("paypal", "Dépannage", 2, 59.0),
    ]
    first = view.echeanciers[0]
    assert (first.mensualite, first.echeance_actuelle, first.nb_echeances, first.mois_debut, first.statut) == (
        35.1, 3, 4, "août 2026", "Actif",
    )


def test_installments_by_name_include_finished_ones() -> None:
    view = tools(installments_state()).get_installments(GetInstallmentsArgs(nom="portable"))
    assert [(i.nom, i.statut) for i in view.echeanciers] == [("Portable", "Terminé")]


def test_installment_unknown_name() -> None:
    with pytest.raises(ToolError, match="paypal"):
        tools(installments_state()).get_installments(GetInstallmentsArgs(nom="voiture"))


# --- Déclarations ----------------------------------------------------------------------------------

def test_declared_tools() -> None:
    names = [tool.name for tool in budget_tool_definitions(tools())]
    assert names == [
        "get_budget_remaining", "get_income", "get_installments", "add_expense", "add_income", "correct_budget_category",
    ]


def test_month_must_be_valid() -> None:
    with pytest.raises(ValueError):
        GetIncomeArgs(mois=13, annee=2026)


# --- Annonce prête à dire (le modèle perdait le signe : « il reste 101 euros » pour −100,69) ---------------

def test_remaining_comes_with_spoken_amounts() -> None:
    view = tools().get_budget_remaining(GetBudgetRemainingArgs(categorie="Restaurant"))
    assert (view.annonce_total, view.annonce_du_mois) == ("budget dépassé de 35 euros", "il reste 45 euros")


@pytest.mark.parametrize("amount, spoken", [
    (923.15, "il reste 923 euros"),
    (0.5, "il reste 1 euro"),
    (0.49, "il ne reste rien"),
    (0.0, "il ne reste rien"),
    (-0.4, "il ne reste rien"),
    (-100.69, "budget dépassé de 101 euros"),
    (-1.2, "budget dépassé de 1 euro"),
])
def test_spoken_remaining(amount: float, spoken: str) -> None:
    from app.core.agent.tools.budget_tools import spoken_remaining
    assert spoken_remaining(amount) == spoken
