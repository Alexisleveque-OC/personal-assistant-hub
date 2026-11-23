"""Outils Budget de l'agent (lecture) : restes par catégorie, revenus, échéanciers via `BudgetConnector`.

La catégorie dictée est rapprochée par le connecteur ; plusieurs possibilités ou aucune → erreur renvoyée au modèle
pour qu'il pose la question (jamais de catégorie inventée).
"""
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from app.connectors.sheets.budget_connector import BudgetConnector, BudgetConnectorError
from app.connectors.sheets.budget_models import BudgetMonth, Installment
from app.core.agent.tools.budget_models import (
    BudgetRemainingView,
    GetBudgetRemainingArgs,
    GetIncomeArgs,
    GetInstallmentsArgs,
    IncomeView,
    InstallmentsView,
    InstallmentView,
)
from app.core.agent.tools.tool_error import ToolError

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
    def __init__(self, connector: Optional[BudgetConnector], unavailable_reason: str = "") -> None:
        """`unavailable_reason` : cause de l'absence de connecteur (identifiant du classeur manquant…)."""
        self._connector = connector
        self._unavailable_reason = unavailable_reason

    @property
    def connector(self) -> BudgetConnector:
        if self._connector is None:
            raise BudgetToolError(f"Le classeur Budget est indisponible : {self._unavailable_reason or 'non configuré'}.")
        return self._connector

    def _resolve(self, spoken: str) -> tuple[str, str]:
        """(catégorie exacte du classeur, rapprochement) ou erreur qui demande de poser la question."""
        resolution = self.connector.resolve_category(spoken)
        if resolution.status == "ambiguous":
            raise BudgetToolError(
                f"Catégorie « {spoken} » ambiguë : {', '.join(c.strip() for c in resolution.candidates)}. "
                "Demande laquelle à l'utilisateur, sans rien supposer."
            )
        if resolution.status == "unknown":
            raise BudgetToolError(
                f"Catégorie « {spoken} » inconnue du budget. Demande à l'utilisateur de préciser la catégorie."
            )
        return resolution.category, _MATCH_LABELS[resolution.source]

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
