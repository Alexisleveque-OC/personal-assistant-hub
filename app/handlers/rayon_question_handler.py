"""Question « dans quel rayon ? » dans /interact : posée par la voie rapide ou l'agent, réponse traitée sans LLM."""
import logging
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel

from app.config import settings
from app.connectors.sheets.meals_connector import MealsShoppingConnector
from app.core.agent.undo import UndoJournal
from app.core.database import get_database_manager
from app.core.llm.rayon_suggester import get_rayon_suggester
from app.core.models import IntentType, ParsedIntent
from app.core.shopping.rayon_questions import RAYON_QUESTION_KEY, PendingRayonQuestion, RayonAnswer, RayonQuestions

logger = logging.getLogger(__name__)

# Réponse sans rapport et trop courte pour être une vraie demande (« euh je sais pas ») : rien d'autre à traiter.
_IDLE_REPLY_MAX_WORDS = 4
_IDLE_INTENTS = frozenset({IntentType.UNKNOWN, IntentType.SMALL_TALK})


class RayonReplyOutcome(BaseModel):
    parsed: ParsedIntent
    spoken: str
    data: Dict[str, Any]
    consumed: bool


def unknown_articles(connector: Any, items: Sequence[str]) -> List[str]:
    """Articles absents du catalogue des rayons (Ingredients_Rayons, Hors_Repas)."""
    unknown = []
    for item in items:
        resolved = connector.resolve_rayon(connector.clean_item_name(item))
        # Connecteur simulé (MagicMock) sans catalogue : tout article est considéré comme connu.
        if isinstance(resolved, tuple) and len(resolved) == 2 and isinstance(resolved[1], str):
            unknown.append(item)
    return unknown


async def ask_rayon_question(articles: Sequence[str], session_ctx: Dict[str, Any], connector: MealsShoppingConnector) -> str:
    """Mémorise la question en session et retourne son texte : rien n'est ajouté avant la réponse."""
    pending, question = await RayonQuestions(connector, get_rayon_suggester()).ask(articles)
    session_ctx[RAYON_QUESTION_KEY] = pending.model_dump()
    return question


async def handle_rayon_reply(
    query: str, session_id: str, session_ctx: Dict[str, Any], connector: Optional[MealsShoppingConnector],
) -> Optional[RayonReplyOutcome]:
    """Traite la réponse à une question de rayon en attente ; None s'il n'y en a pas."""
    raw = session_ctx.pop(RAYON_QUESTION_KEY, None)
    if raw is None:
        return None
    pending = PendingRayonQuestion.model_validate(raw)
    if connector is None:
        logger.warning(f"Question de rayon pour « {pending.article} » abandonnée : classeur Repas & Courses indisponible.")
        return None

    answer = await RayonQuestions(connector, get_rayon_suggester()).answer(query, pending)
    data: Dict[str, Any] = {}
    if answer.added:
        data["items"] = [item.model_dump() for item in answer.added]  # toast « article(s) ajouté(s) »
        _journalize(session_id, session_ctx, answer)
    if answer.next_question:
        session_ctx[RAYON_QUESTION_KEY] = data["rayon_question"] = answer.next_question.model_dump()
    rayon = answer.added[0].rayon if answer.added and answer.consumed else None
    return RayonReplyOutcome(
        parsed=ParsedIntent(intent=IntentType.CHOOSE_RAYON, confidence=1.0, parameters={"rayon": rayon}, raw_query=query),
        spoken=answer.spoken,
        data=data,
        consumed=answer.consumed,
    )


def is_idle_reply(parsed: ParsedIntent, query: str) -> bool:
    return parsed.intent in _IDLE_INTENTS and len(query.split()) <= _IDLE_REPLY_MAX_WORDS


def _journalize(session_id: str, session_ctx: Dict[str, Any], answer: RayonAnswer) -> None:
    """« Annule ça » : annulation exacte par le journal en mode agent (article + rayon appris), legacy sinon."""
    UndoJournal(get_database_manager()).record(session_id, list(answer.undos))
    if settings.nlu_mode == "agent":
        session_ctx.pop("last_undoable_action", None)
    else:
        session_ctx["last_undoable_action"] = {"type": "add_shopping_item", "items": [it.item for it in answer.added]}
