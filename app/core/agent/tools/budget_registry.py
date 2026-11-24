"""Déclaration des outils Budget exposés à l'agent Gemini — jamais à l'expert Claude (coût des déclarations)."""
from typing import Callable, List, Optional

from app.connectors.sheets.budget_models import BudgetEntry
from app.core.agent.tool_registry import AgentTool
from app.core.agent.tools.budget_models import (
    AddExpenseArgs,
    AddIncomeArgs,
    AddInstallmentArgs,
    BudgetMutation,
    CorrectBudgetCategoryArgs,
    ForgetBudgetAliasArgs,
    GetBudgetRemainingArgs,
    GetIncomeArgs,
    GetInstallmentsArgs,
    PredeclareSplitExpenseArgs,
)
from app.core.agent.tools.budget_tools import BudgetTools


def budget_tool_definitions(
    tools: BudgetTools, last_entry: Callable[[], Optional[BudgetEntry]] = lambda: None,
) -> List[AgentTool]:
    """`last_entry` : dernière ligne budget écrite par Otis dans la conversation (lue dans le journal d'annulation)."""
    def correct_budget_category(args: CorrectBudgetCategoryArgs) -> BudgetMutation:
        return tools.correct_category(args, last_entry())

    return [
        AgentTool(
            name="get_budget_remaining",
            description=(
                "Budget : argent restant dans une catégorie de dépense (« combien il reste en course ? ») ou un groupe "
                "(loisir, courants…). Renvoie le reste total de la catégorie et le reste fin du mois du mois actif "
                "(ou du mois demandé), et la catégorie retenue."
            ),
            args_model=GetBudgetRemainingArgs,
            handler=tools.get_budget_remaining,
        ),
        AgentTool(
            name="get_income",
            description=(
                "Budget : revenus reçus sur un mois calendaire (« combien j'ai touché en CAF ce mois-ci ? »), "
                "pour un type de revenu ou tous."
            ),
            args_model=GetIncomeArgs,
            handler=tools.get_income,
        ),
        AgentTool(
            name="get_installments",
            description=(
                "Budget : échéanciers (paiements en plusieurs fois) actifs, ou suivi d'un échéancier précis par son "
                "nom (échéance actuelle, échéances et montant restants)."
            ),
            args_model=GetInstallmentsArgs,
            handler=tools.get_installments,
        ),
        AgentTool(
            name="add_expense",
            description=(
                "Budget : enregistre une dépense (« j'ai dépensé 20 € en course », « 12 € de resto en ticket resto ») "
                "ou un remboursement reçu (remboursement=true) dans une catégorie de dépense, à la date du jour sauf "
                "date dite. Écrit tout de suite, sans confirmation."
            ),
            args_model=AddExpenseArgs,
            handler=tools.add_expense,
        ),
        AgentTool(
            name="add_income",
            description=(
                "Budget : enregistre un revenu reçu (« j'ai touché 150 € de CAF ») dans un type de revenu, à la date du "
                "jour sauf date dite."
            ),
            args_model=AddIncomeArgs,
            handler=tools.add_income,
        ),
        AgentTool(
            name="correct_budget_category",
            description=(
                "Budget : change la catégorie de la dépense ou du revenu qu'Otis vient d'enregistrer "
                "(« non, c'était dans la catégorie X »). Refuse si la ligne a été modifiée depuis."
            ),
            args_model=CorrectBudgetCategoryArgs,
            handler=correct_budget_category,
        ),
        AgentTool(
            name="add_installment",
            description=(
                "Budget : crée un échéancier pour un achat payé en plusieurs fois (« j'ai payé 400 € en 4 fois chez "
                "Ikea, en maison ») ; l'import bancaire rapprochera chaque mensualité. Écrit tout de suite."
            ),
            args_model=AddInstallmentArgs,
            handler=tools.add_installment,
        ),
        AgentTool(
            name="predeclare_split_expense",
            description=(
                "Budget : pré-déclare une dépense multiple (« dépense d'avance ») qui sera débitée en une fois mais "
                "répartie entre plusieurs catégories (« 62 € chez Amazon : 33 en cadeaux, 29 en course ») ; l'import "
                "bancaire découpera le débit. La somme des parts doit égaler le total. Écrit tout de suite."
            ),
            args_model=PredeclareSplitExpenseArgs,
            handler=tools.predeclare_split_expense,
        ),
        AgentTool(
            name="forget_budget_alias",
            description=(
                "Budget : oublie un nom de catégorie qu'Otis avait appris (« oublie loisir alexis ») ; la prochaine "
                "fois, il reposera la question « lequel ? »."
            ),
            args_model=ForgetBudgetAliasArgs,
            handler=tools.forget_alias,
        ),
    ]
