"""Phase 10, étape 1 : lecture du classeur Budget (faux classeur hors-ligne, aucun appel à Google)."""
from datetime import date

import pytest

from app.connectors.sheets.budget_connector import (
    ActiveMonthNotFoundError,
    BudgetCategoryNotFoundError,
    BudgetConnector,
    BudgetConnectorError,
    BudgetGroupError,
    BudgetHeaderError,
    BudgetMonthNotFoundError,
    BudgetWorksheetNotFoundError,
    InstallmentNotFoundError,
    open_budget_spreadsheet,
)
from app.connectors.sheets.budget_models import BudgetMonth
from tests.budget_fakes import (
    BudgetSheetState,
    GestionLine,
    Installment,
    build_budget_spreadsheet,
    serial,
)

TODAY = date(2026, 11, 23)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make(state: BudgetSheetState = None, clock: Clock = None, today: date = TODAY):
    sheet = build_budget_spreadsheet(state or BudgetSheetState())
    connector = BudgetConnector(sheet, monotonic=clock or Clock(), today=lambda: today)
    return connector, sheet


# --- Catégories et tri auto -------------------------------------------------------------------

def test_categories_keep_exact_names_and_dates() -> None:
    connector, _ = make()
    categories = {c.name: c for c in connector.get_categories()}
    assert "Cadeaux Elias " in categories  # espace final conservé (valeur de la liste déroulante)
    assert categories["Course"].created == date(2024, 1, 1)
    assert categories["Course"].ended is None
    assert categories["Vacances 2025"].ended == date(2025, 12, 31)


def test_active_categories_exclude_ended_ones() -> None:
    connector, _ = make()
    names = [c.name for c in connector.get_categories(active_only=True)]
    assert "Vacances 2025" not in names
    assert "Course" in names


def test_auto_sort_rules() -> None:
    connector, _ = make()
    rules = connector.get_auto_sort_rules()
    assert rules[0].keyword == "totalenergies electricite"
    assert rules[0].category == "Elec"


# --- Mois actif ---------------------------------------------------------------------------------

def test_active_month_is_last_checked_month() -> None:
    connector, _ = make()
    assert connector.get_active_month() == BudgetMonth(year=2026, month=11)


def test_active_month_missing_raises_explicit_error() -> None:
    connector, _ = make(BudgetSheetState(checked=()))
    with pytest.raises(ActiveMonthNotFoundError, match="ligne 4"):
        connector.get_active_month()


def test_budget_month_label_and_previous() -> None:
    assert BudgetMonth(year=2026, month=11).label == "novembre 2026"
    assert BudgetMonth(year=2026, month=1).previous() == BudgetMonth(year=2025, month=12)


# --- Reste par catégorie ----------------------------------------------------------------------

def test_remaining_total_and_active_month() -> None:
    connector, _ = make()
    remaining = connector.get_remaining("course")
    assert remaining.category == "Course"
    assert remaining.total_remaining == 412.5
    assert remaining.month == BudgetMonth(year=2026, month=11)
    assert remaining.month_remaining == 230.0


def test_remaining_for_explicit_month() -> None:
    connector, _ = make()
    remaining = connector.get_remaining("Restaurant", month=BudgetMonth(year=2026, month=10))
    assert remaining.month_remaining == -10.0
    assert remaining.total_remaining == -35.2


def test_remaining_ignores_accents_case_and_trailing_spaces() -> None:
    connector, _ = make()
    assert connector.get_remaining("cadeaux elias").category == "Cadeaux Elias "
    assert connector.get_remaining("Epargne candice").total_remaining == 1500.0


def test_remaining_category_also_named_like_its_group() -> None:
    connector, _ = make()
    assert connector.get_remaining("Epargne").total_remaining == 300.0


def test_remaining_of_a_group_is_refused_with_its_categories() -> None:
    connector, _ = make()
    with pytest.raises(BudgetGroupError, match="Loisir Alex") as exc:
        connector.get_remaining("Loisir")
    assert "groupe" in str(exc.value)


def test_remaining_unknown_category_lists_available_ones() -> None:
    connector, _ = make()
    with pytest.raises(BudgetCategoryNotFoundError, match="Course") as exc:
        connector.get_remaining("Piscine")
    assert "Piscine" in str(exc.value)


def test_remaining_month_absent_from_gestion() -> None:
    connector, _ = make()
    with pytest.raises(BudgetMonthNotFoundError, match="janvier 2027") as exc:
        connector.get_remaining("Course", month=BudgetMonth(year=2027, month=1))
    assert "novembre 2026" in str(exc.value)


# --- Revenus -------------------------------------------------------------------------------------

def income_state() -> BudgetSheetState:
    return BudgetSheetState(income=(
        (date(2026, 10, 5), 267.41, "caf"),
        (date(2026, 11, 5), 267.41, "CAF"),
        (date(2026, 11, 20), 30.0, "Caf"),
        (date(2026, 11, 28), 1800.0, "Salaire Alexis"),
        (date(2026, 12, 1), 99.0, "CAF"),
    ))


def test_income_sums_type_and_month_ignoring_case() -> None:
    connector, _ = make(income_state())
    summary = connector.get_income("CAF", BudgetMonth(year=2026, month=11))
    assert summary.total == pytest.approx(297.41)
    assert summary.count == 2
    assert summary.income_type == "CAF"
    assert summary.month == BudgetMonth(year=2026, month=11)


def test_income_without_entries_is_zero() -> None:
    connector, _ = make(income_state())
    summary = connector.get_income("Salaire Alexis", BudgetMonth(year=2026, month=10))
    assert summary.total == 0
    assert summary.count == 0


def test_income_ignores_blank_rows() -> None:
    connector, sheet = make(income_state())
    sheet.worksheet("Revenus").rows.append(["", "", ""])
    assert connector.get_income("CAF", BudgetMonth(year=2026, month=11)).count == 2


def test_income_invalid_amount_names_the_row() -> None:
    connector, sheet = make(income_state())
    sheet.worksheet("Revenus").rows.append([serial(date(2026, 11, 2)), "abc", "CAF"])
    with pytest.raises(BudgetConnectorError, match="ligne 7"):
        connector.get_income("CAF", BudgetMonth(year=2026, month=11))


# --- Échéanciers ----------------------------------------------------------------------------------

def installments_state() -> BudgetSheetState:
    return BudgetSheetState(installments=(
        Installment("Portable", 308.99, 4, 4, 77.25, date(2026, 5, 1), "Dépannage", status="Terminé"),
        Installment("paypal", 140.38, 4, 3, 35.1, date(2026, 8, 1), "Chats"),
        Installment("paypal", 118.0, 4, 2, 29.5, date(2026, 9, 1), "Dépannage", comment="billet de train"),
    ))


def test_installments_active_only_by_default() -> None:
    connector, _ = make(installments_state())
    installments = connector.get_installments()
    assert [(i.name, i.category) for i in installments] == [("paypal", "Chats"), ("paypal", "Dépannage")]
    first = installments[0]
    assert first.start_month == BudgetMonth(year=2026, month=8)
    assert first.remaining_count == 1
    assert first.remaining_amount == pytest.approx(35.1)
    assert installments[1].comment == "billet de train"


def test_installments_all() -> None:
    connector, _ = make(installments_state())
    assert len(connector.get_installments(active_only=False)) == 3


def test_find_installments_returns_every_match() -> None:
    connector, _ = make(installments_state())
    assert len(connector.find_installments("PayPal")) == 2
    assert connector.find_installments("portable")[0].status == "Terminé"


def test_find_installment_unknown_lists_names() -> None:
    connector, _ = make(installments_state())
    with pytest.raises(InstallmentNotFoundError, match="paypal"):
        connector.find_installments("voiture")


# --- Résolution de catégorie -------------------------------------------------------------------

@pytest.mark.parametrize("spoken, expected", [
    ("course", "Course"),
    ("  RESTAURANT ", "Restaurant"),
    ("cadeaux elias", "Cadeaux Elias "),
])
def test_resolve_exact_category(spoken: str, expected: str) -> None:
    connector, _ = make()
    resolution = connector.resolve_category(spoken)
    assert (resolution.status, resolution.category, resolution.source) == ("resolved", expected, "category")


@pytest.mark.parametrize("spoken, expected", [
    ("croquettes", "Chats"),            # mot-clé exact
    ("Leclerc", "Course"),
    ("électricité", "Elec"),            # mot du mot-clé « totalenergies electricite »
    ("courses chez Carrefour", "Course"),  # mot-clé contenu dans la phrase
])
def test_resolve_through_auto_sort(spoken: str, expected: str) -> None:
    connector, _ = make()
    resolution = connector.resolve_category(spoken)
    assert (resolution.status, resolution.category, resolution.source) == ("resolved", expected, "auto_sort")


def test_resolve_auto_sort_with_several_categories_is_ambiguous() -> None:
    connector, _ = make()
    resolution = connector.resolve_category("amazon prime")
    assert resolution.status == "ambiguous"
    assert resolution.category is None
    assert resolution.candidates == ["Chats", "Loisir Alex"]


def test_resolve_close_name_is_a_question_not_a_guess() -> None:
    connector, _ = make()
    resolution = connector.resolve_category("cadeau elias")
    assert resolution.status == "ambiguous"
    assert resolution.category is None
    assert "Cadeaux Elias " in resolution.candidates


def test_resolve_unknown() -> None:
    connector, _ = make()
    resolution = connector.resolve_category("piscine")
    assert (resolution.status, resolution.category, resolution.candidates) == ("unknown", None, [])


def test_resolve_ignores_ended_categories() -> None:
    connector, _ = make()
    assert connector.resolve_category("vacances 2025").status != "resolved"


def test_resolve_empty_is_refused() -> None:
    connector, _ = make()
    with pytest.raises(ValueError, match="vide"):
        connector.resolve_category("  ")


# --- Structure du classeur (fail-fast) ------------------------------------------------------------

def test_missing_worksheet_lists_available_tabs() -> None:
    sheet = build_budget_spreadsheet(BudgetSheetState())
    del sheet._worksheets["Échéanciers"]
    connector = BudgetConnector(sheet, monotonic=Clock(), today=lambda: TODAY)
    with pytest.raises(BudgetWorksheetNotFoundError, match="Échéanciers") as exc:
        connector.get_installments()
    assert "Gestion" in str(exc.value)


def test_header_drift_is_explicit() -> None:
    connector, sheet = make()
    sheet.worksheet("Échéanciers").rows[0][8] = "État"
    with pytest.raises(BudgetHeaderError, match="Statut"):
        connector.get_installments()


def test_gestion_month_block_drift_is_explicit() -> None:
    connector, sheet = make()
    sheet.worksheet("Gestion").rows[0][7] = "Reste"  # en-tête du 1er bloc mensuel (colonne H)
    with pytest.raises(BudgetHeaderError, match="Reste fin du mois"):
        connector.get_remaining("Course", month=BudgetMonth(year=2026, month=9))


# --- Cache ---------------------------------------------------------------------------------------

def test_reads_are_cached_three_minutes_per_tab() -> None:
    clock = Clock()
    connector, sheet = make(clock=clock)
    gestion = sheet.worksheet("Gestion")
    connector.get_remaining("Course")
    connector.get_remaining("Chats")
    assert gestion.reads == 1
    clock.now += 179
    connector.get_remaining("Course")
    assert gestion.reads == 1
    clock.now += 2
    connector.get_remaining("Course")
    assert gestion.reads == 2


def test_invalidate_cache_of_one_tab_or_all() -> None:
    connector, sheet = make()
    connector.get_remaining("Course")
    connector.get_categories()
    connector.invalidate_cache("Gestion")
    connector.get_remaining("Course")
    connector.get_categories()
    assert sheet.worksheet("Gestion").reads == 2
    assert sheet.worksheet("Catégories").reads == 1
    connector.invalidate_cache()
    connector.get_categories()
    assert sheet.worksheet("Catégories").reads == 2


# --- Ouverture du classeur -----------------------------------------------------------------------

def test_open_budget_spreadsheet_requires_the_id() -> None:
    class Settings:
        spreadsheet_budget_id = "  "

    with pytest.raises(BudgetConnectorError, match="SPREADSHEET_BUDGET_ID"):
        open_budget_spreadsheet(Settings())


def test_remaining_amounts_are_rounded_to_the_cent() -> None:
    state = BudgetSheetState(groups=(("Courants", (GestionLine("Course", 923.1539999999998, {(2026, 11): 0.1 + 0.2}),)),))
    connector, _ = make(state)
    remaining = connector.get_remaining("Course")
    assert (remaining.total_remaining, remaining.month_remaining) == (923.15, 0.3)
