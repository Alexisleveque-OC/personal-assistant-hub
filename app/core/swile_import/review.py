"""Relecture d'un import Swile (sans écriture) : captures lues → lignes datées, catégorisées, doublons signalés.

Décisions utilisateur du 26/11 : catégorie par `Tri auto` (mot-clé contenu dans le marchand ou l'inverse) puis noms
appris ; crédit → « Ticket resto » ; doublon =
même montant à ±3 jours dans `Swile` (dépense) ou `Revenus` (crédit), une ligne du classeur ne couvrant qu'une ligne
capturée ; lignes identiques de plusieurs captures fusionnées ; lignes illisibles ignorées et signalées.
"""
from collections import Counter
from datetime import date
from typing import Dict, List, Optional, Protocol, Tuple

from app.connectors.sheets.budget_connector import (
    INCOME_GROUP,
    INCOME_SHEET,
    SWILE_SHEET,
    BudgetConnector,
    normalize,
)
from app.connectors.sheets.budget_models import RecordedEntry
from app.core.swile_import.dates import parse_swile_date
from app.core.swile_import.models import (
    SwileBalanceView,
    SwileCapture,
    SwileCaptureLine,
    SwileReview,
    SwileReviewLine,
)

DUPLICATE_WINDOW_DAYS = 3
CREDIT_CATEGORY = "Ticket resto"


class AliasLookup(Protocol):
    def get_budget_alias(self, alias: str) -> Optional[str]: ...


class SwileReviewError(Exception):
    """Rien d'importable sur les captures ; le message cite chaque raison (422 côté routeur)."""


def _euros(amount: float) -> str:
    return f"{amount:.2f} €".replace(".", ",")


def _readable_lines(captures: List[SwileCapture], reference: date) -> Tuple[List[SwileReviewLine], List[str]]:
    """Lignes lisibles, fusionnées entre captures (un même achat vu deux fois), et avertissements."""
    warnings: List[str] = []
    kept: Dict[Tuple[date, float, str], int] = {}
    first_seen: Dict[Tuple[date, float, str], SwileCaptureLine] = {}
    for number, capture in enumerate(captures, start=1):
        if not capture.is_swile:
            warnings.append(f"Capture {number} ignorée : {capture.message or 'ce n’est pas une capture Swile.'}")
            continue
        counts: Counter = Counter()
        for raw in capture.lignes:
            day = parse_swile_date(raw.date_texte, reference)
            if day is None or round(raw.montant, 2) == 0 or not raw.marchand.strip():
                warnings.append(
                    f"Ligne illisible ignorée : {raw.marchand.strip() or '?'} (« {raw.date_texte} », {_euros(raw.montant)})."
                )
                continue
            key = (day, round(raw.montant, 2), normalize(raw.marchand))
            counts[key] += 1
            first_seen.setdefault(key, raw)
        for key, count in counts.items():  # deux achats identiques sur UNE capture restent deux lignes
            kept[key] = max(kept.get(key, 0), count)
    lines = [
        SwileReviewLine(
            type="credit" if amount > 0 else "depense", date=day, montant=abs(amount),
            marchand=first_seen[(day, amount, merchant)].marchand.strip(), cochee=True,
        )
        for (day, amount, merchant), count in kept.items()
        for _ in range(count)
    ]
    lines.sort(key=lambda line: line.date, reverse=True)
    return lines, warnings


class _Categorizer:
    def __init__(self, connector: BudgetConnector, aliases: Optional[AliasLookup]) -> None:
        income = {normalize(name) for name in connector.group_members(INCOME_GROUP)}
        active = [c.name for c in connector.get_categories(active_only=True)]
        self._expenses = {
            normalize(name): name for name in active
            if normalize(name) not in income and not connector.group_members(name)
        }
        self._credit = next((name for name in active if normalize(name) in income
                             and normalize(name) == normalize(CREDIT_CATEGORY)), None)
        self._rules = connector.get_auto_sort_rules()
        self._aliases = aliases

    def __call__(self, line: SwileReviewLine) -> Optional[str]:
        if line.type == "credit":
            return self._credit
        merchant = f" {normalize(line.marchand)} "
        # Dans les deux sens, comme `resolve_category` : les mots-clés de `Tri auto` sont des libellés bancaires
        # (« intermarche la jarrie »), souvent plus longs que le nom affiché par Swile (« Intermarche »).
        by_rule = {
            normalize(rule.category) for rule in self._rules
            if normalize(rule.keyword)
            and (f" {normalize(rule.keyword)} " in merchant or merchant in f" {normalize(rule.keyword)} ")
        }
        if len(by_rule) == 1:
            return self._expenses.get(by_rule.pop())  # None si la règle vise un groupe ou une catégorie terminée
        if by_rule or self._aliases is None:
            return None
        learned = self._aliases.get_budget_alias(normalize(line.marchand))
        return None if learned is None else self._expenses.get(normalize(learned))


def _mark_duplicates(lines: List[SwileReviewLine], recorded: Dict[str, List[RecordedEntry]]) -> List[SwileReviewLine]:
    used: Dict[str, set] = {sheet: set() for sheet in recorded}
    marked = []
    for line in lines:
        sheet = INCOME_SHEET if line.type == "credit" else SWILE_SHEET
        candidates = [
            (abs((entry.day - line.date).days), index) for index, entry in enumerate(recorded[sheet])
            if index not in used[sheet] and round(entry.amount, 2) == round(line.montant, 2)
            and abs((entry.day - line.date).days) <= DUPLICATE_WINDOW_DAYS
        ]
        if not candidates:
            marked.append(line)
            continue
        index = min(candidates)[1]
        used[sheet].add(index)
        entry = recorded[sheet][index]
        marked.append(line.model_copy(update={
            "cochee": False, "doublon": f"déjà saisie le {entry.day:%d/%m} ({entry.category}) ?",
        }))
    return marked


def build_review(
    captures: List[SwileCapture], connector: BudgetConnector, aliases: Optional[AliasLookup], reference: date,
) -> SwileReview:
    lines, warnings = _readable_lines(captures, reference)
    balance = next((capture.solde for capture in captures if capture.is_swile and capture.solde is not None), None)
    if not lines and balance is None:
        raise SwileReviewError(" ".join(warnings) or "Aucune ligne ni solde Swile lisible sur les captures.")

    categorize = _Categorizer(connector, aliases)
    lines = [line.model_copy(update={"categorie": categorize(line)}) for line in lines]
    recorded = {sheet: connector.get_entries(sheet) for sheet in (SWILE_SHEET, INCOME_SHEET)}
    lines = _mark_duplicates(lines, recorded)

    balance_view = None
    if balance is not None:
        cell = connector.get_swile_balance()
        balance_view = SwileBalanceView(nouveau=round(balance, 2), actuel=cell.value, mois=cell.month.label)
    return SwileReview(lignes=lines, solde=balance_view, avertissements=warnings)
