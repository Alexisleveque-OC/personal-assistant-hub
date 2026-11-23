"""Outils Budget de l'agent : restes par catégorie, revenus, échéanciers, saisies (dépense, revenu, correction).

La catégorie dictée est rapprochée par le connecteur ; plusieurs possibilités ou aucune → erreur renvoyée au modèle
pour qu'il pose la question (jamais de catégorie inventée). Une saisie n'est jamais écrite sur un nom de groupe
(question « laquelle ? ») ; un revenu ne prend qu'une catégorie du groupe Revenus.
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, List, Optional

from app.connectors.sheets.budget_connector import INCOME_SHEET, BudgetConnector, BudgetConnectorError
from app.connectors.sheets.budget_models import BudgetEntry, BudgetMonth, Installment
from app.core.agent.tools.budget_models import (
    AddExpenseArgs,
    AddIncomeArgs,
    BudgetCategoryChangedUndo,
    BudgetEntryAddedUndo,
    BudgetEntryView,
    BudgetMutation,
    BudgetRemainingView,
    BudgetUndo,
    CorrectBudgetCategoryArgs,
    GetBudgetRemainingArgs,
    GetIncomeArgs,
    GetInstallmentsArgs,
    IncomeView,
    InstallmentsView,
    InstallmentView,
)
from app.core.agent.tools.tool_error import ToolError
from app.core.clock import paris_today

INCOME_GROUP = "Revenus"
LABEL_PREFIX = "Otis : "
_MATCH_LABELS = {"category": "exact", "auto_sort": "tri_auto", "close_match": "nom_proche"}


def spoken_remaining(amount: float) -> str:
    """Reste arrondi à l'euro, signe interprété : le modèle oubliait le signe (« il reste 101 euros » pour −100,69)."""
    euros = int(Decimal(str(abs(amount))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if euros == 0:
        return "il ne reste rien"
    unit = "euro" if euros == 1 else "euros"
    return f"il reste {euros} {unit}" if amount > 0 else f"budget dépassé de {euros} {unit}"


class BudgetToolError(ToolError):
    """Erreur Budget renvoyée telle quelle au modèle."""


class BudgetTools:
    def __init__(
        self, connector: Optional[BudgetConnector], unavailable_reason: str = "", today: Callable[[], date] = paris_today,
    ) -> None:
        """`unavailable_reason` : cause de l'absence de connecteur (identifiant du classeur manquant…)."""
        self._connector = connector
        self._unavailable_reason = unavailable_reason
        self._today = today

    @property
    def connector(self) -> BudgetConnector:
        if self._connector is None:
            raise BudgetToolError(f"Le classeur Budget est indisponible : {self._unavailable_reason or 'non configuré'}.")
        return self._connector

    def _resolve(self, spoken: str, among: Optional[List[str]] = None) -> tuple[str, str]:
        """(catégorie exacte du classeur, rapprochement) ou erreur qui demande de poser la question.

        `among` : catégories permises (revenus) ; une catégorie inconnue cite alors la liste des choix.
        """
        resolution = self.connector.resolve_category(spoken, among=among)
        if resolution.status == "ambiguous":
            raise BudgetToolError(
                f"Catégorie « {spoken} » ambiguë : {', '.join(c.strip() for c in resolution.candidates)}. "
                "Demande laquelle à l'utilisateur, sans rien supposer."
            )
        if resolution.status == "unknown" and among is not None:
            raise BudgetToolError(
                f"« {spoken} » n'est pas un type de revenu du budget. Types possibles : "
                f"{', '.join(c.strip() for c in among)}. Demande lequel à l'utilisateur."
            )
        if resolution.status == "unknown":
            raise BudgetToolError(
                f"Catégorie « {spoken} » inconnue du budget. Demande à l'utilisateur de préciser la catégorie."
            )
        return resolution.category, _MATCH_LABELS[resolution.source]

    def _resolve_for_entry(self, spoken: str, sheet: str) -> tuple[str, str]:
        """Catégorie où écrire : groupe Revenus pour un revenu ; jamais un nom de groupe (question « laquelle ? »)."""
        if sheet == INCOME_SHEET:
            return self._resolve(spoken, among=self.connector.group_members(INCOME_GROUP))
        category, match = self._resolve(spoken)
        members = self.connector.group_members(category)
        if members:
            raise BudgetToolError(
                f"« {category.strip()} » est un groupe : {', '.join(m.strip() for m in members)}. "
                "Demande dans laquelle de ces catégories écrire, sans rien supposer."
            )
        return category, match

    def get_budget_remaining(self, args: GetBudgetRemainingArgs) -> BudgetRemainingView:
        try:
            category, match = self._resolve(args.categorie)
            month = None
            if args.mois is not None:
                year = args.annee if args.annee is not None else self.connector.get_active_month().year
                month = BudgetMonth(year=year, month=args.mois)
            remaining = self.connector.get_remaining(category, month=month)
        except BudgetConnectorError as exc:
            raise BudgetToolError(str(exc)) from exc
        return BudgetRemainingView(
            categorie=remaining.category.strip(),
            categorie_dite=args.categorie,
            rapprochement=match,
            reste_total=remaining.total_remaining,
            annonce_total=spoken_remaining(remaining.total_remaining),
            mois=remaining.month.label,
            reste_du_mois=remaining.month_remaining,
            annonce_du_mois=spoken_remaining(remaining.month_remaining),
            categories_du_groupe=[name.strip() for name in remaining.group_categories],
        )

    def get_income(self, args: GetIncomeArgs) -> IncomeView:
        try:
            income_type = None if args.type is None else self._resolve(args.type)[0]
            summary = self.connector.get_income(income_type, BudgetMonth(year=args.annee, month=args.mois))
        except BudgetConnectorError as exc:
            raise BudgetToolError(str(exc)) from exc
        return IncomeView(
            type=None if income_type is None else income_type.strip(),
            mois=summary.month.label,
            total=summary.total,
            nombre=summary.count,
        )

    def get_installments(self, args: GetInstallmentsArgs) -> InstallmentsView:
        try:
            found = self.connector.get_installments() if args.nom is None else self.connector.find_installments(args.nom)
        except BudgetConnectorError as exc:
            raise BudgetToolError(str(exc)) from exc
        return InstallmentsView(echeanciers=[_installment_view(i) for i in found])


    # --- Saisies ----------------------------------------------------------------------------------

    def add_expense(self, args: AddExpenseArgs) -> BudgetMutation:
        sheet = "Swile" if args.swile else "Débit"
        amount = -args.montant if args.remboursement else args.montant
        action = "remboursement_ajoute" if args.remboursement else "depense_ajoutee"
        return self._add(sheet, amount, args.categorie, args.libelle, args.date, action)

    def add_income(self, args: AddIncomeArgs) -> BudgetMutation:
        return self._add(INCOME_SHEET, args.montant, args.type, args.libelle, args.date, "revenu_ajoute")

    def _add(self, sheet: str, amount: float, spoken: str, libelle: str, day: Optional[date], action: str) -> BudgetMutation:
        try:
            category, match = self._resolve_for_entry(spoken, sheet)
            entry = BudgetEntry(
                sheet=sheet, day=day or self._today(), amount=round(amount, 2), category=category,
                label=f"{LABEL_PREFIX}{libelle}",
            )
            self.connector.add_entry(entry)
        except BudgetConnectorError as exc:
            raise BudgetToolError(str(exc)) from exc
        return BudgetMutation(action=action, ligne=_entry_view(entry, match), undos=[BudgetEntryAddedUndo(entry=entry)])

    def correct_category(self, args: CorrectBudgetCategoryArgs, last: Optional[BudgetEntry]) -> BudgetMutation:
        """« Non, c'était dans X » : catégorie de la dernière ligne écrite par Otis, seulement si elle est inchangée."""
        if last is None:
            raise BudgetToolError(
                "Aucune dépense ni aucun revenu écrit par Otis juste avant dans cette conversation : rien à corriger."
            )
        try:
            category, match = self._resolve_for_entry(args.categorie, last.sheet)
            if category.strip() == last.category.strip():
                raise BudgetToolError(f"La ligne « {last.label} » est déjà en {category.strip()}.")
            changed = self.connector.set_entry_category(last, category)
        except BudgetConnectorError as exc:
            raise BudgetToolError(str(exc)) from exc
        return BudgetMutation(
            action="categorie_corrigee", ligne=_entry_view(changed, match), ancienne_categorie=last.category.strip(),
            undos=[BudgetCategoryChangedUndo(entry=changed, previous_category=last.category)],
        )

    # --- Annulation (appelée par `UndoService`) ---------------------------------------------------

    @staticmethod
    def undo_targets(undo: BudgetUndo) -> List[tuple]:
        entry = undo.entry
        return [("budget_entry", entry.sheet, entry.day, entry.amount, entry.label)]

    def check_undo(self, undo: BudgetUndo) -> None:
        """Annulation refusée si la ligne a été supprimée ou modifiée depuis (retrouvée par son contenu)."""
        try:
            self.connector.require_entry_row(undo.entry)
        except BudgetConnectorError as exc:
            raise BudgetToolError(f"Annulation impossible : {exc}") from exc

    def apply_undo(self, undo: BudgetUndo) -> str:
        entry = undo.entry
        try:
            if isinstance(undo, BudgetEntryAddedUndo):
                self.connector.delete_entry(entry)
                return f"ligne « {entry.label} » supprimée du budget ({entry.sheet})"
            self.connector.set_entry_category(entry, undo.previous_category)
        except BudgetConnectorError as exc:
            raise BudgetToolError(str(exc)) from exc
        return f"ligne « {entry.label} » remise en {undo.previous_category.strip()}"


def _entry_view(entry: BudgetEntry, match: str) -> BudgetEntryView:
    return BudgetEntryView(
        onglet=entry.sheet, date=entry.day, montant=entry.amount, categorie=entry.category.strip(),
        intitule=entry.label, rapprochement=match,
    )


def _installment_view(installment: Installment) -> InstallmentView:
    return InstallmentView(
        nom=installment.name,
        categorie=installment.category.strip(),
        mensualite=installment.monthly_amount,
        echeance_actuelle=installment.current_installment,
        nb_echeances=installment.installments_count,
        echeances_restantes=installment.remaining_count,
        montant_restant=installment.remaining_amount,
        mois_debut=installment.start_month.label,
        statut=installment.status,
        commentaire=installment.comment,
    )
