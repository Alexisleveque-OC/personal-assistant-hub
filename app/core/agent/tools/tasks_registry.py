"""Déclaration de l'outil Tâches exposé à l'agent."""
from typing import List

from app.core.agent.tool_registry import AgentTool
from app.core.agent.tools.tasks_models import GetTasksArgs
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
    ]
