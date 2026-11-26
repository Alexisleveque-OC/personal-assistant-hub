"""Outils Budget de l'agent : restes par catégorie, revenus, échéanciers, saisies (dépense, revenu, correction),
création d'échéanciers et pré-déclaration de dépenses multiples.

La catégorie dictée est rapprochée par le connecteur ; plusieurs possibilités ou aucune → erreur renvoyée au modèle
pour qu'il pose la question (jamais de catégorie inventée). Une saisie n'est jamais écrite sur un nom de groupe
(question « laquelle ? ») ; un revenu ne prend qu'une catégorie du groupe Revenus.

Noms appris (étape 5 bis, décisions du 24/11) : la réponse à une question « lequel ? » est retenue (base de l'app) et
resservira sans question ; un nom exact du classeur l'emporte toujours ; « non, c'était dans X » n'apprend rien.
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, List, Optional

from pydantic import ValidationError

from app.connectors.sheets.budget_connector import (
    DEBIT_SHEET,
    INCOME_SHEET,
    INSTALLMENT_ACTIVE,
    SPLIT_TO_PROCESS,
    BudgetConnector,
    BudgetConnectorError,
    normalize,
)
from app.connectors.sheets.budget_models import (
    BudgetEntry,
    BudgetMonth,
    Installment,
    NewInstallment,
    SplitExpense,
    SplitPart,
)
from app.core.agent.tools.budget_models import (
    AddExpenseArgs,
    AddIncomeArgs,
    AddInstallmentArgs,
    BudgetAliasLearnedUndo,
    BudgetCategoryChangedUndo,
    BudgetEntryAddedUndo,
    BudgetEntryView,
    BudgetMutation,
    BudgetRemainingView,
    BudgetUndo,
    CorrectBudgetCategoryArgs,
    ForgetBudgetAliasArgs,
    ForgottenAliasView,
    GetBudgetRemainingArgs,
    GetIncomeArgs,
    GetInstallmentsArgs,
    IncomeView,
    InstallmentAddedUndo,
    InstallmentMutation,
    InstallmentsView,
    InstallmentView,
    PredeclareSplitExpenseArgs,
    SplitDeclaredUndo,
    SwileImportUndo,
    SplitExpenseView,
    SplitMutation,
    SplitPartView,
)
from app.core.agent.tools.budget_pending import PendingCategoryQuestions
from app.core.agent.tools.tool_error import ToolError
from app.core.clock import paris_today
from app.core.database.budget_aliases import BudgetAliasStore

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
        aliases: Optional[BudgetAliasStore] = None, session_id: str = "", pending: Optional[PendingCategoryQuestions] = None,
    ) -> None:
        """`unavailable_reason` : cause de l'absence de connecteur (identifiant du classeur manquant…).

        `aliases` / `pending` / `session_id` : noms appris et question « lequel ? » en attente de la conversation
        (absents = ni apprentissage ni noms appris).
        """
        self._connector = connector
        self._unavailable_reason = unavailable_reason
        self._today = today
        self._aliases = aliases
        self._session_id = session_id
        self._pending = pending

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
        if resolution.status == "resolved" and resolution.source == "category":
            return resolution.category, _MATCH_LABELS["category"]
        learned = self._learned_category(spoken, among)
        if learned is not None:
            return learned, "appris"
        if resolution.status == "ambiguous":
            if self._pending is not None:
                self._pending.ask(self._session_id, normalize(spoken), resolution.candidates)
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

    def _learned_category(self, spoken: str, among: Optional[List[str]]) -> Optional[str]:
        """Catégorie exacte d'un nom appris, si elle existe encore (et est permise) ; sinon None."""
        if self._aliases is None:
            return None
        learned = self._aliases.get_budget_alias(normalize(spoken))
        if learned is None:
            return None
        names = among if among is not None else [c.name for c in self.connector.get_categories(active_only=True)]
        return next((name for name in names if normalize(name) == normalize(learned)), None)

    def _answered(self, categories: List[str]) -> Optional[tuple[str, str]]:
        """(nom dit, catégorie) si cet appel répond à la question « lequel ? » en attente (consommée)."""
        if self._pending is None or self._aliases is None:
            return None
        return self._pending.take(self._session_id, categories)

    def _learn(self, answer: Optional[tuple[str, str]]) -> tuple[Optional[str], List[BudgetAliasLearnedUndo]]:
        """Enregistre le nom appris : (phrase pour le modèle, annulation à joindre à l'écriture)."""
        if answer is None:
            return None, []
        alias, category = answer
        self._aliases.learn_budget_alias(alias, category)
        return f"« {alias} » = {category}", [BudgetAliasLearnedUndo(alias=alias, category=category)]

    def forget_alias(self, args: ForgetBudgetAliasArgs) -> ForgottenAliasView:
        """« Oublie loisir alexis » : la question « lequel ? » reviendra, et sa réponse sera réapprise."""
        if self._aliases is None:
            raise BudgetToolError("Les noms de catégorie appris sont indisponibles.")
        alias = normalize(args.nom)
        category = self._aliases.get_budget_alias(alias)
        if category is None or not self._aliases.forget_budget_alias(alias):
            known = self._aliases.list_budget_aliases()
            listed = ", ".join(f"« {name} » ({cat})" for name, cat in known.items()) or "aucun"
            raise BudgetToolError(f"Aucun nom de catégorie appris « {args.nom} ». Noms appris : {listed}.")
        return ForgottenAliasView(nom=alias, categorie=category)

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
        learned, _ = self._learn(self._answered([category]))
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
            nom_appris=learned,
        )

    def get_income(self, args: GetIncomeArgs) -> IncomeView:
        try:
            income_type = None if args.type is None else self._resolve(args.type)[0]
            summary = self.connector.get_income(income_type, BudgetMonth(year=args.annee, month=args.mois))
        except BudgetConnectorError as exc:
            raise BudgetToolError(str(exc)) from exc
        learned, _ = self._learn(self._answered([income_type])) if income_type is not None else (None, [])
        return IncomeView(
            type=None if income_type is None else income_type.strip(),
            mois=summary.month.label,
            total=summary.total,
            nombre=summary.count,
            nom_appris=learned,
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
        learned, learned_undos = self._learn(self._answered([category]))
        return BudgetMutation(
            action=action, ligne=_entry_view(entry, match), nom_appris=learned,
            undos=[BudgetEntryAddedUndo(entry=entry), *learned_undos],
        )

    def correct_category(self, args: CorrectBudgetCategoryArgs, last: Optional[BudgetEntry]) -> BudgetMutation:
        """« Non, c'était dans X » : catégorie de la dernière ligne écrite par Otis, seulement si elle est inchangée."""
        if last is None:
            raise BudgetToolError(
                "Aucune dépense ni aucun revenu écrit par Otis juste avant dans cette conversation : rien à corriger."
            )
        self._answered([])  # une correction répond à la question sans rien apprendre (décision du 24/11)
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

    # --- Échéanciers et dépenses multiples ---------------------------------------------------------

    def add_installment(self, args: AddInstallmentArgs) -> InstallmentMutation:
        """Échéancier « Actif » à l'échéance 0, à partir du mois en cours sauf mois dit (déjà passé → l'an prochain)."""
        today = self._today()
        start = BudgetMonth(year=today.year, month=today.month)
        if args.mois_debut is not None:
            year = args.annee_debut
            if year is None:
                year = today.year + (1 if args.mois_debut < today.month else 0)
            start = BudgetMonth(year=year, month=args.mois_debut)
        try:
            category, match = self._resolve_for_entry(args.categorie, DEBIT_SHEET)
            installment = NewInstallment(
                name=args.nom, total_amount=round(args.montant_total, 2), count=args.nb_echeances, start_month=start,
                category=category, comment=args.commentaire.strip(),
            )
            self.connector.add_installment(installment)
        except BudgetConnectorError as exc:
            raise BudgetToolError(str(exc)) from exc
        learned, learned_undos = self._learn(self._answered([category]))
        view = _installment_view(Installment(
            name=installment.name, total_amount=installment.total_amount, installments_count=installment.count,
            current_installment=0, monthly_amount=installment.monthly_amount, start_month=start, category=category,
            comment=installment.comment, status=INSTALLMENT_ACTIVE,
        ))
        return InstallmentMutation(
            echeancier=view, rapprochement=match, nom_appris=learned,
            undos=[InstallmentAddedUndo(installment=installment), *learned_undos],
        )

    def predeclare_split_expense(self, args: PredeclareSplitExpenseArgs) -> SplitMutation:
        """Dépense multiple « A traiter » : l'import découpera le débit bancaire correspondant entre les catégories."""
        try:
            resolved = [(self._resolve_for_entry(part.categorie, DEBIT_SHEET), part.montant) for part in args.parts]
            split = SplitExpense(
                day=args.date or self._today(), keyword=args.mot_cle, total_amount=round(args.montant_total, 2),
                parts=tuple(SplitPart(category=category, amount=round(amount, 2)) for (category, _), amount in resolved),
            )
        except BudgetConnectorError as exc:
            raise BudgetToolError(str(exc)) from exc
        except ValidationError as exc:
            raise BudgetToolError(
                "; ".join(error["msg"].removeprefix("Value error, ") for error in exc.errors())
                + " Redemande la répartition à l'utilisateur."
            ) from exc
        try:
            self.connector.add_split_expense(split)
        except BudgetConnectorError as exc:
            raise BudgetToolError(str(exc)) from exc
        learned, learned_undos = self._learn(self._answered([category for (category, _), _ in resolved]))
        view = SplitExpenseView(
            date=split.day, mot_cle=split.keyword, montant_total=split.total_amount, statut=SPLIT_TO_PROCESS,
            parts=[
                SplitPartView(categorie=category.strip(), montant=amount, rapprochement=match)
                for (category, match), amount in resolved
            ],
        )
        return SplitMutation(depense=view, nom_appris=learned, undos=[SplitDeclaredUndo(split=split), *learned_undos])

    # --- Annulation (appelée par `UndoService`) ---------------------------------------------------

    @staticmethod
    def undo_targets(undo: BudgetUndo) -> List[tuple]:
        if isinstance(undo, SwileImportUndo):
            targets = [("budget_entry", e.sheet, e.day, e.amount, e.label) for e in undo.entries]
            return targets + ([("budget_swile_balance", undo.balance.month)] if undo.balance else [])
        if isinstance(undo, InstallmentAddedUndo):
            i = undo.installment
            return [("budget_installment", i.name, i.total_amount, i.count, i.start_month)]
        if isinstance(undo, SplitDeclaredUndo):
            return [("budget_split", undo.split.day, undo.split.keyword, undo.split.total_amount)]
        entry = undo.entry
        return [("budget_entry", entry.sheet, entry.day, entry.amount, entry.label)]

    def check_undo(self, undo: BudgetUndo) -> None:
        """Annulation refusée si la ligne a été supprimée ou modifiée depuis (retrouvée par son contenu)."""
        if isinstance(undo, SwileImportUndo):
            self._check_swile_import(undo)
            return
        try:
            self.connector.require_entry_row(_written(undo))
        except BudgetConnectorError as exc:
            raise BudgetToolError(f"Annulation impossible : {exc}") from exc

    def _check_swile_import(self, undo: SwileImportUndo) -> None:
        try:
            self.connector.require_entry_rows(undo.entries)
            if undo.balance is not None:
                current = self.connector.get_swile_balance(undo.balance.month, fresh=True)
                if current.value != undo.balance.written:
                    raise BudgetToolError(
                        f"Annulation impossible : la case « Reste Swile » de {undo.balance.month.label} a été modifiée "
                        "depuis l'import."
                    )
        except BudgetConnectorError as exc:
            raise BudgetToolError(f"Annulation impossible : {exc}") from exc

    def _undo_swile_import(self, undo: SwileImportUndo) -> str:
        self.connector.delete_entries(undo.entries)
        if undo.balance is not None:
            self.connector.set_swile_balance(undo.balance.month, undo.balance.previous, expected=undo.balance.written)
        balance = " et solde Swile remis" if undo.balance else ""
        return f"import Swile annulé ({len(undo.entries)} ligne(s) supprimée(s){balance})"

    def apply_undo(self, undo: BudgetUndo) -> str:
        try:
            if isinstance(undo, SwileImportUndo):
                return self._undo_swile_import(undo)
            if isinstance(undo, InstallmentAddedUndo):
                self.connector.delete_entry(undo.installment)
                return f"échéancier « {undo.installment.name} » supprimé du budget"
            if isinstance(undo, SplitDeclaredUndo):
                self.connector.delete_entry(undo.split)
                return f"dépense multiple « {undo.split.keyword} » supprimée du budget"
            entry = undo.entry
            if isinstance(undo, BudgetEntryAddedUndo):
                self.connector.delete_entry(entry)
                return f"ligne « {entry.label} » supprimée du budget ({entry.sheet})"
            self.connector.set_entry_category(entry, undo.previous_category)
        except BudgetConnectorError as exc:
            raise BudgetToolError(str(exc)) from exc
        return f"ligne « {entry.label} » remise en {undo.previous_category.strip()}"


def _written(undo: BudgetUndo) -> BudgetEntry | NewInstallment | SplitExpense:
    """Ligne du classeur visée par une annulation."""
    if isinstance(undo, InstallmentAddedUndo):
        return undo.installment
    if isinstance(undo, SplitDeclaredUndo):
        return undo.split
    return undo.entry


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
