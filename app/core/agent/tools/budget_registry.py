"""Déclaration des outils Budget (lecture) exposés à l'agent Gemini — jamais à l'expert Claude (coût des déclarations)."""
from typing import List

from app.core.agent.tool_registry import AgentTool
from app.core.agent.tools.budget_models import GetBudgetRemainingArgs, GetIncomeArgs, GetInstallmentsArgs
from app.core.agent.tools.budget_tools import BudgetTools


def budget_tool_definitions(tools: BudgetTools) -> List[AgentTool]:
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
    ]
