"""Types de séance cités par l'utilisateur, déduits par le code à partir de ses mots.

Garde-fou anti-ambiguïté : ce vocabulaire fermé ne déclenche jamais d'action, il permet seulement
de refuser une modification quand un jour compte plusieurs séances et qu'aucune n'a été désignée.
"""
import re
from typing import Iterable, Set

from app.connectors.sheets.sport_models import SportSessionType

_TYPE_WORDS = {
    SportSessionType.RENFORCEMENT: r"renfo|renforcement|muscu|musculation|gainage|ppg",
    SportSessionType.EF: r"ef|endurance(?:\s+fondamentale)?|footing",
    SportSessionType.FRACTIONNE: r"fractionn[ée]|vma|intervalles?",
    SportSessionType.SORTIE_LONGUE: r"sortie\s+longue",
    SportSessionType.TEMPO: r"tempo",
    SportSessionType.VITESSE: r"vitesse",
    SportSessionType.RECUP: r"r[ée]cup(?:[ée]ration)?",
}
_PATTERNS = {t: re.compile(rf"\b(?:{words})\b", re.IGNORECASE) for t, words in _TYPE_WORDS.items()}


def cited_session_types(texts: Iterable[str]) -> Set[SportSessionType]:
    return {t for text in texts for t, pattern in _PATTERNS.items() if pattern.search(text)}
