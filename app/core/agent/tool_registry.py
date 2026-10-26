"""Registre des outils exposés au LLM : déclarations Gemini et exécution validée par Pydantic.

Les erreurs métier et d'arguments sont renvoyées au modèle (`{"error": ...}`) pour qu'il se corrige
ou demande une précision ; les erreurs inattendues (bugs) remontent telles quelles (fail-fast).
"""
from dataclasses import dataclass
import inspect
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

from pydantic import BaseModel, Field, ValidationError

from app.core.agent.gemini_schema import to_gemini_schema
from app.core.agent.tools.sport_models import MutationResult, SessionView
from app.core.agent.tools.sport_tools import SportToolError
from app.core.agent.undo import AgentUndo

logger = logging.getLogger(__name__)

ToolResult = Union[BaseModel, List[BaseModel]]


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[Any], Union[ToolResult, Awaitable[ToolResult]]]

    def declaration(self) -> Dict[str, Any]:
        declaration: Dict[str, Any] = {"name": self.name, "description": self.description}
        parameters = to_gemini_schema(self.args_model)
        if parameters.get("properties"):  # Gemini refuse un objet sans propriétés
            declaration["parameters"] = parameters
        return declaration


class ToolExecution(BaseModel):
    """Trace d'un appel d'outil : arguments reçus, réponse renvoyée au modèle, instantanés des mutations."""
    name: str
    args: Dict[str, Any]
    response: Dict[str, Any]
    error: Optional[str] = None
    undos: List[AgentUndo] = Field(default_factory=list)


class ToolRegistry:
    def __init__(self, tools: List[AgentTool]) -> None:
        names = [t.name for t in tools]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise ValueError(f"Noms d'outils dupliqués : {duplicates}")
        self._tools = {t.name: t for t in tools}

    def declarations(self) -> List[Dict[str, Any]]:
        return [tool.declaration() for tool in self._tools.values()]

    async def execute(self, name: str, raw_args: Dict[str, Any]) -> ToolExecution:
        tool = self._tools.get(name)
        if tool is None:
            return self._failure(name, raw_args, f"Outil inconnu « {name} ». Outils disponibles : {sorted(self._tools)}.")
        try:
            result = tool.handler(tool.args_model.model_validate(raw_args))
            if inspect.isawaitable(result):
                result = await result
        except ValidationError as exc:
            details = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
            return self._failure(name, raw_args, f"Arguments invalides pour {name} : {details}")
        except SportToolError as exc:
            return self._failure(name, raw_args, str(exc))

        if isinstance(result, MutationResult):
            response = {"action": result.undo.action, "session": result.session.model_dump(mode="json")}
            return ToolExecution(name=name, args=raw_args, response=response, undos=[result.undo])
        if isinstance(result, list):
            return ToolExecution(name=name, args=raw_args, response={"sessions": [r.model_dump(mode="json") for r in result]})
        if isinstance(result, SessionView):
            return ToolExecution(name=name, args=raw_args, response={"session": result.model_dump(mode="json")})
        # Résultat composite : ses instantanés éventuels (`undos`) restent côté serveur.
        undos = list(getattr(result, "undos", []))
        response = result.model_dump(mode="json", exclude={"undos"})
        return ToolExecution(name=name, args=raw_args, response=response, undos=undos)

    @staticmethod
    def _failure(name: str, raw_args: Dict[str, Any], message: str) -> ToolExecution:
        logger.info(f"Outil agent {name} en erreur : {message}")
        return ToolExecution(name=name, args=raw_args, response={"error": message}, error=message)
