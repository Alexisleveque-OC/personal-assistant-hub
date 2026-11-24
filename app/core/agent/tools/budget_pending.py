"""Question « lequel ? » en attente de réponse, par conversation : source de l'apprentissage des noms de catégorie.

Quand une catégorie dite est ambiguë, Otis pose la question avec les choix proposés ; si la saisie (ou la lecture)
suivante de la même conversation retient l'une de ces catégories, le nom dit est appris. Gardée en mémoire seulement
(10 min) : un redémarrage fait au pire perdre un apprentissage, la question reviendra.
"""
import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple

PENDING_TTL_SECONDS = 600


class PendingCategoryQuestions:
    def __init__(self, ttl_seconds: float = PENDING_TTL_SECONDS, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._ttl_seconds = ttl_seconds
        self._monotonic = monotonic
        self._questions: Dict[str, Tuple[float, str, List[str]]] = {}

    def ask(self, session_id: str, spoken: str, candidates: Sequence[str]) -> None:
        """`spoken` : nom dit, normalisé ; `candidates` : catégories exactes proposées."""
        self._questions[session_id] = (self._monotonic(), spoken, [c.strip() for c in candidates])

    def take(self, session_id: str, categories: Sequence[str]) -> Optional[Tuple[str, str]]:
        """(nom dit, catégorie) à apprendre si une seule des `categories` retenues par l'appel suivant répond à la
        question en attente ; la question est consommée dans tous les cas (une autre réponse ne l'apprend pas)."""
        question = self._questions.pop(session_id, None)
        if question is None:
            return None
        asked_at, spoken, candidates = question
        if self._monotonic() - asked_at > self._ttl_seconds:
            return None
        answers = {category.strip() for category in categories} & set(candidates)
        if len(answers) != 1:
            return None
        return spoken, answers.pop()


_pending = PendingCategoryQuestions()


def get_pending_category_questions() -> PendingCategoryQuestions:
    return _pending
