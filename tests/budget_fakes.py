"""Doublure en mémoire du classeur Google Sheets « Budget » (hors-ligne, données fictives : dépôt public).

Reproduit la structure du vrai classeur relevée le 23/11 : valeurs brutes (`UNFORMATTED_VALUE`), dates en
numéros de série Sheets, `Gestion` avec un bloc de 3 colonnes par mois à partir de F (mois en ligne 2) et des
groupes (ligne d'en-tête après une ligne vide, puis « Total » / « Total: »), mois actif = dernière case cochée
en ligne 4 de `Total dépenses` à partir de la colonne D.
"""
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple

from tests.meals_fakes import FakeSpreadsheet

SHEETS_EPOCH = date(1899, 12, 30)
GESTION_FIRST_MONTH_COL = 6  # F, 1-indexé
GESTION_FIRST_GROUP_ROW = 12


def serial(day: date) -> int:
    """Numéro de série Sheets d'une date (comme `UNFORMATTED_VALUE`)."""
    return (day - SHEETS_EPOCH).days


class BudgetFakeWorksheet:
    """Onglet à valeurs typées (nombres, booléens, chaînes) ; compte les lectures pour tester le cache.

    Écritures : `update` en `USER_ENTERED` (une date ISO devient un numéro de série, comme dans Sheets), limitée à
    `row_count` lignes comme la grille réelle (`add_rows` l'agrandit), et `delete_rows`.
    """

    def __init__(self, title: str, rows: Sequence[Sequence[Any]], spare_rows: int = 20) -> None:
        self.title = title
        self.rows: List[List[Any]] = [list(row) for row in rows]
        self.reads = 0
        self.row_count = len(self.rows) + spare_rows
        self.writes: List[Tuple[str, List[List[Any]]]] = []
        self.formats: List[Dict[str, Any]] = []

    def get_all_values(self, value_render_option: Optional[str] = None, **_: Any) -> List[List[Any]]:
        if value_render_option != "UNFORMATTED_VALUE":
            raise AssertionError(f"Le connecteur budget doit lire les valeurs brutes, reçu {value_render_option!r}")
        self.reads += 1
        width = max((len(row) for row in self.rows), default=0)
        last = max((i + 1 for i, row in enumerate(self.rows) if any(not _blank(v) for v in row)), default=0)
        return [list(row) + [""] * (width - len(row)) for row in self.rows[:last]]

    def update(self, range_name: str, values: List[List[Any]], value_input_option: Optional[str] = None) -> None:
        if value_input_option != "USER_ENTERED":
            raise AssertionError(f"Écriture budget attendue en USER_ENTERED, reçu {value_input_option!r}")
        match = re.fullmatch(r"([A-Z])(\d+)(?::([A-Z])(\d+))?", range_name)
        if match is None:
            raise ValueError(f"Plage non supportée par la doublure : {range_name!r}")
        row, col = int(match.group(2)), ord(match.group(1)) - ord("A")
        if row > self.row_count:
            raise ValueError(f"Plage {range_name} hors de la grille ({self.row_count} lignes) : add_rows d'abord.")
        self.writes.append((range_name, values))
        while len(self.rows) < row:
            self.rows.append([])
        target = self.rows[row - 1]
        for offset, value in enumerate(values[0]):
            while len(target) <= col + offset:
                target.append("")
            target[col + offset] = _user_entered(value)

    def batch_format(self, formats: List[Dict[str, Any]]) -> None:
        """Formats de nombre (monnaie, mois) : enregistrés tels quels, sans effet sur les valeurs."""
        self.formats.extend(formats)

    def add_rows(self, count: int) -> None:
        self.row_count += count

    def delete_rows(self, index: int) -> None:
        del self.rows[index - 1]
        self.row_count -= 1


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _user_entered(value: Any) -> Any:
    """Interprétation `USER_ENTERED` du sous-ensemble utilisé : date ISO → numéro de série, le reste tel quel."""
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return serial(date.fromisoformat(value))
    return value


@dataclass
class GestionLine:
    """Ligne catégorie de `Gestion` : reste total (colonne B) et reste fin du mois par mois."""
    name: str
    total_remaining: float
    month_remaining: Dict[Tuple[int, int], float] = field(default_factory=dict)


@dataclass
class Installment:
    name: str
    total: float
    count: int
    current: int
    monthly: float
    start: date
    category: str
    comment: str = ""
    status: str = "Actif"


DEFAULT_GROUPS: Tuple[Tuple[str, Tuple[GestionLine, ...]], ...] = (
    ("Courants", (
        GestionLine("Course", 412.5, {(2026, 10): 12.4, (2026, 11): 230.0}),
        GestionLine("Restaurant", -35.2, {(2026, 10): -10.0, (2026, 11): 45.0}),
        GestionLine("Chats", 80.0, {(2026, 10): 5.0, (2026, 11): 60.0}),
    )),
    ("Loisir", (
        GestionLine("Loisir Alex", 120.0, {(2026, 10): 0.0, (2026, 11): 25.0}),
        GestionLine("Cadeaux Elias ", 50.0, {(2026, 10): 0.0, (2026, 11): 50.0}),
    )),
    ("Fixes", (
        GestionLine("Elec", 199.0, {(2026, 10): 0.0, (2026, 11): 0.0}),
    )),
    ("Epargne", (
        GestionLine("épargne Candice", 1500.0, {(2026, 10): 0.0, (2026, 11): 0.0}),
        GestionLine("Epargne", 300.0, {(2026, 10): 0.0, (2026, 11): 100.0}),
    )),
    ("Revenus", (
        GestionLine("Salaire Alexis", 10.0, {(2026, 10): 0.0, (2026, 11): 0.0}),
        GestionLine("CAF", -20.0, {(2026, 10): 0.0, (2026, 11): 0.0}),
    )),
)
DEFAULT_CATEGORIES: Tuple[Tuple[str, date, Optional[date]], ...] = tuple(
    (line.name, date(2024, 1, 1), None) for _, lines in DEFAULT_GROUPS for line in lines
) + tuple((group, date(2024, 1, 1), None) for group, _ in DEFAULT_GROUPS) + (
    ("Vacances 2025", date(2025, 1, 1), date(2025, 12, 31)),
)
DEFAULT_AUTO_SORT: Tuple[Tuple[str, str], ...] = (
    ("totalenergies electricite", "Elec"),
    ("carrefour", "Course"),
    ("leclerc", "Course"),
    ("croquettes", "Chats"),
    ("animalerie", "Chats"),
    ("mcdo", "Restaurant"),
    ("mcdonalds", "Restaurant"),
    ("amazon", "Loisir Alex"),
    ("amazon prime", "Chats"),
)


@dataclass
class BudgetSheetState:
    """État initial du classeur. `months` : mois présents dans Gestion / Total dépenses ; `checked` : cochés."""
    months: Sequence[Tuple[int, int]] = ((2026, 9), (2026, 10), (2026, 11), (2026, 12))
    checked: Sequence[Tuple[int, int]] = ((2026, 9), (2026, 10), (2026, 11))
    groups: Sequence[Tuple[str, Sequence[GestionLine]]] = DEFAULT_GROUPS
    categories: Sequence[Tuple[str, date, Optional[date]]] = DEFAULT_CATEGORIES
    auto_sort: Sequence[Tuple[str, str]] = DEFAULT_AUTO_SORT
    income: Sequence[Tuple[date, float, str]] = ()
    installments: Sequence[Installment] = ()
    debits: Sequence[Tuple[date, float, str, str, str]] = ()  # Date | Montant | Type | Commentaires | Intitulé
    swile: Sequence[Tuple[date, float, str, str]] = ()  # Date | Montant | Type | Commentaires
    # Date approximative | Mot-clé banque | Montant total | Statut | Description | Parts JSON
    splits: Sequence[Tuple[date, str, float, str, str, str]] = ()
    spare_rows: int = 20  # lignes vides sous les données (0 = onglet plein, comme Revenus et Échéanciers le 24/11)


def build_budget_spreadsheet(state: BudgetSheetState) -> FakeSpreadsheet:
    return FakeSpreadsheet([
        BudgetFakeWorksheet("Total dépenses", _total_rows(state)),
        BudgetFakeWorksheet("Gestion", _gestion_rows(state)),
        BudgetFakeWorksheet("Catégories", [["Catégorie", "Date de création", "Date de fin"]] + [
            [name, serial(created), serial(ended) if ended else ""] for name, created, ended in state.categories
        ]),
        BudgetFakeWorksheet("Tri auto", [["Nom", "Catégorie"]] + [list(rule) for rule in state.auto_sort]),
        BudgetFakeWorksheet("Revenus", [["Date", "Montant", "Type", "Commentaires", "Intitulé"]] + [
            [serial(day), amount, kind] for day, amount, kind in state.income
        ], spare_rows=state.spare_rows),
        # Débit : colonne E (intitulé) sans en-tête, comme le vrai classeur ; Swile : 4 colonnes.
        BudgetFakeWorksheet("Débit", [["Date", "Montant", "Type", "Commentaires", ""]] + [
            [serial(day), amount, kind, comment, label] for day, amount, kind, comment, label in state.debits
        ], spare_rows=state.spare_rows),
        BudgetFakeWorksheet("Swile", [["Date", "Montant", "Type", "Commentaires"]] + [
            [serial(day), amount, kind, comment] for day, amount, kind, comment in state.swile
        ], spare_rows=state.spare_rows),
        BudgetFakeWorksheet("Échéanciers", [[
            "Nom du Projet", "Montant Total", "Nb Échéances", "Échéance Actuelle", "Mensualité", "Mois Début",
            "Catégorie", "Commentaires", "Statut",
        ]] + [
            [i.name, i.total, i.count, i.current, i.monthly, serial(i.start), i.category, i.comment, i.status]
            for i in state.installments
        ], spare_rows=state.spare_rows),
        BudgetFakeWorksheet("Dépenses Multiples", [[
            "Date Approximative", "Mot-clé Banque", "Montant Total", "Statut", "Description du Split", "Splits JSON",
        ]] + [[serial(day), *rest] for day, *rest in state.splits], spare_rows=state.spare_rows),
    ])


def _total_rows(state: BudgetSheetState) -> List[List[Any]]:
    months = [serial(date(y, m, 1)) for y, m in state.months]
    checks = [(y, m) in state.checked for y, m in state.months]
    return [
        [],
        ["Type", "2024", "2025", *months, "2026", "Moyenne total"],
        ["Quotient24", 12, 12, *["f"] * len(months)],
        ["nbr: mois", "", "", *checks, sum(checks)],
        ["Total dépense", 5066.9, 4806.74, *[100.0] * len(months)],
    ]


def _gestion_rows(state: BudgetSheetState) -> List[List[Any]]:
    header = ["2025", "Reste", "Marge", "retour 2025", ""]
    months_row = ["Mois", "", "", "", "Prévus base"]
    for y, m in state.months:
        header += ["Prévu", "Equilibrage", "Reste fin du mois"]
        months_row += [serial(date(y, m, 1)), "D", ""]
    rows: List[List[Any]] = [header, months_row]
    for label in ("Reste à réinjecté", "N° Mois", "Démarré", "Cloturé", "Reste Estimé", "Reste compte",
                  "Reste Swile", "Différence"):
        rows.append([label, 999.0])
    rows.append([])
    assert len(rows) == GESTION_FIRST_GROUP_ROW - 1
    for group, lines in state.groups:
        rows.append([group, 0.0])
        for line in lines:
            row: List[Any] = [line.name, line.total_remaining, 300.0, "", 300.0]
            for month in state.months:
                row += [300.0, "", line.month_remaining.get(month, 0.0)]
            rows.append(row)
        rows.append(["Total:", sum(line.total_remaining for line in lines)])
        rows.append([])
    rows += [[], ["Totaux dépenses"], ["Total des revenus"], ["Différence"]]
    return rows
