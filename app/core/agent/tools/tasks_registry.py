"""Déclaration des outils Tâches exposés à l'agent."""
from typing import List

from app.core.agent.tool_registry import AgentTool
from app.core.agent.tools.tasks_models import AddTaskArgs, CompleteTaskArgs, GetTasksArgs
from app.core.agent.tools.tasks_tools import TasksTools


def tasks_tool_definitions(tools: TasksTools) -> List[AgentTool]:
    return [
        AgentTool(
            name="get_tasks",
            description=(
                "Lit les tâches non terminées de la liste Google Tasks « Mes tâches » de l'utilisateur : titre, "
                "échéance éventuelle (jour de la semaine, en retard ou non) et notes. Les tâches avec échéance "
                "viennent d'abord, par date. Sans rapport avec la liste de courses."
            ),
            args_model=GetTasksArgs,
            handler=tools.get_tasks,
        ),
        AgentTool(
            name="add_task",
            description=(
                "Ajoute une tâche à la liste Google Tasks « Mes tâches » (« rappelle-moi de… », « ajoute une tâche… », "
                "« penser à… », « il faut que je… »), avec son jour d'échéance s'il est dit."
            ),
            args_model=AddTaskArgs,
            handler=tools.add_task,
        ),
        AgentTool(
            name="complete_task",
            description="Coche (termine) une tâche de « Mes tâches » par son identifiant, lu au préalable avec get_tasks.",
            args_model=CompleteTaskArgs,
            handler=tools.complete_task,
        ),
    ]
