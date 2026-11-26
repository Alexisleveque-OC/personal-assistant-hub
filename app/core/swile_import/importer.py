"""Écriture d'un import Swile relu (Phase 10, étape 8) : dépenses → `Swile`, crédits → `Revenus`, solde → « Reste
Swile » du mois actif. Toutes les catégories sont vérifiées avant la moindre écriture ; une écriture refusée en cours
de route retire les lignes déjà écrites (jamais d'import à moitié fait sans annulation possible).
"""
import logging
from typing import Dict, List, Optional

from app.connectors.sheets.budget_connector import (
    INCOME_GROUP,
    INCOME_SHEET,
    SWILE_SHEET,
    BudgetConnector,
    BudgetConnectorError,
    normalize,
)
from app.connectors.sheets.budget_models import BudgetEntry
from app.core.agent.tools.budget_models import SwileBalanceChange, SwileImportUndo
from app.core.swile_import.models import SwileImportForm, SwileImportLine

logger = logging.getLogger(__name__)
COMMENT_PREFIX = "Swile : "


class SwileImportError(Exception):
    """Import refusé avant toute écriture (catégorie) ; message destiné à l'utilisateur (422)."""


class SwileRollbackError(BudgetConnectorError):
    """Écriture refusée en cours d'import ET lignes déjà écrites impossibles à retirer : le message les liste."""


class _Categories:
    def __init__(self, connector: BudgetConnector) -> None:
        self._connector = connector
        self.income = {normalize(name): name for name in connector.group_members(INCOME_GROUP)}
        self.active = {normalize(c.name): c.name for c in connector.get_categories(active_only=True)}

    def exact(self, line: SwileImportLine) -> str:
        where = f"ligne {line.marchand} du {line.date:%d/%m}"
        wanted = normalize(line.categorie)
        if line.type == "credit":
            if wanted not in self.income:
                raise SwileImportError(
                    f"« {line.categorie} » n'est pas un type de revenu ({where}). Types possibles : "
                    f"{', '.join(name.strip() for name in self.income.values())}."
                )
            return self.income[wanted]
        if wanted in self.income:
            raise SwileImportError(f"« {line.categorie} » est un type de revenu, pas une catégorie de dépense ({where}).")
        if wanted not in self.active:
            raise SwileImportError(f"Catégorie « {line.categorie} » inconnue du budget ({where}).")
        members = self._connector.group_members(self.active[wanted])
        if members:
            raise SwileImportError(
                f"« {line.categorie} » est un groupe ({where}) : choisis une de ses catégories "
                f"({', '.join(m.strip() for m in members)})."
            )
        return self.active[wanted]


def _entries(connector: BudgetConnector, form: SwileImportForm) -> List[BudgetEntry]:
    categories = _Categories(connector)
    return [
        BudgetEntry(
            sheet=INCOME_SHEET if line.type == "credit" else SWILE_SHEET, day=line.date, amount=round(line.montant, 2),
            category=categories.exact(line), label=f"{COMMENT_PREFIX}{line.marchand}",
        )
        for line in form.lignes
    ]


def _roll_back(connector: BudgetConnector, written: List[BudgetEntry], cause: Exception) -> None:
    if not written:
        return
    try:
        connector.delete_entries(written)
    except Exception as exc:
        logger.error(f"Import Swile : retour arrière impossible après « {cause} » : {exc}")
        raise SwileRollbackError(
            f"{cause} — et les {len(written)} ligne(s) déjà écrite(s) n'ont pas pu être retirées ({exc}) : "
            f"{', '.join(f'{e.label} {e.amount:.2f} € le {e.day:%d/%m}' for e in written)}. À supprimer à la main."
        ) from cause


def import_swile(connector: BudgetConnector, form: SwileImportForm) -> SwileImportUndo:
    entries = _entries(connector, form)
    by_sheet: Dict[str, List[BudgetEntry]] = {SWILE_SHEET: [], INCOME_SHEET: []}
    for entry in entries:
        by_sheet[entry.sheet].append(entry)

    written: List[BudgetEntry] = []
    balance: Optional[SwileBalanceChange] = None
    try:
        for sheet, batch in by_sheet.items():
            connector.add_entries(sheet, batch)
            written += batch
        if form.solde is not None:
            cell = connector.get_swile_balance(fresh=True)
            new_value = round(form.solde, 2)
            connector.set_swile_balance(cell.month, new_value, expected=cell.value)
            balance = SwileBalanceChange(month=cell.month, previous=cell.value, written=new_value)
    except Exception as exc:
        _roll_back(connector, written, exc)
        raise
    return SwileImportUndo(entries=written, balance=balance)
