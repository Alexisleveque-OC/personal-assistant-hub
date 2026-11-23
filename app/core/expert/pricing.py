"""Tarifs de l'API Claude (en $ par million de tokens, relevés le 03/11/2026) et coût d'un appel de l'expert.

Écriture en cache (5 min) = 1,25 × le tarif d'entrée. Le repli serveur peut répondre avec un autre modèle :
un modèle absent du tableau est compté au tarif connu le plus cher (estimation prudente, signalée dans les logs).
"""
import logging
from typing import Dict, NamedTuple

from app.core.expert.llm import ExpertUsage

logger = logging.getLogger(__name__)


class ModelPrice(NamedTuple):
    input: float
    output: float
    cache_read: float

    @property
    def cache_write(self) -> float:
        return self.input * 1.25


PRICES_PER_MTOK: Dict[str, ModelPrice] = {
    "claude-sonnet-5-5": ModelPrice(input=2.00, output=10.00, cache_read=0.10),
    "claude-sonnet-5": ModelPrice(input=2.00, output=10.00, cache_read=0.20),
    "claude-opus-4-8": ModelPrice(input=5.00, output=25.00, cache_read=0.50),
}
_MOST_EXPENSIVE = max(PRICES_PER_MTOK.values(), key=lambda p: p.output)


def usage_cost_usd(usage: ExpertUsage) -> float:
    price = PRICES_PER_MTOK.get(usage.model or "")
    if price is None:
        logger.warning(f"Tarif inconnu pour le modèle Claude « {usage.model} » : compté au tarif connu le plus cher.")
        price = _MOST_EXPENSIVE
    return (
        usage.input_tokens * price.input
        + usage.output_tokens * price.output
        + usage.cache_read_input_tokens * price.cache_read
        + usage.cache_creation_input_tokens * price.cache_write
    ) / 1_000_000
