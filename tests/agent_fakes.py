"""Doublures de test de l'agent : LLM scripté, déterministe et hors-ligne."""
from typing import Any, Dict, List, Optional

from app.core.agent.llm import LLMTurn


def text_turn(text: str) -> LLMTurn:
    return LLMTurn(parts=[{"text": text}], finish_reason="STOP")


def call_turn(*calls: Dict[str, Any], signature: Optional[str] = "sig-1") -> LLMTurn:
    """Tour modèle composé d'appels de fonction ; la signature est portée par le premier appel (doc Gemini 3)."""
    parts = []
    for index, call in enumerate(calls):
        part: Dict[str, Any] = {"functionCall": call}
        if index == 0 and signature:
            part["thoughtSignature"] = signature
        parts.append(part)
    return LLMTurn(parts=parts, finish_reason="STOP")


class ScriptedLLM:
    """Rejoue une suite de tours prédéfinis et mémorise chaque requête reçue."""

    def __init__(self, turns: List[Any]) -> None:
        self._turns = list(turns)
        self.requests: List[Dict[str, Any]] = []

    async def generate(self, *, system_instruction: str, contents: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> LLMTurn:
        self.requests.append({
            "system_instruction": system_instruction,
            "contents": [dict(c) for c in contents],
            "tools": tools,
        })
        if not self._turns:
            raise AssertionError("ScriptedLLM : plus aucun tour scripté disponible.")
        turn = self._turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn
