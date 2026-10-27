"""Article au rayon inconnu : l'application demande le rayon à l'utilisateur et retient sa réponse.

Logique unique pour la voie rapide regex (« ajoute X ») et l'outil agent `add_shopping_items` :
1. Question : rien n'est ajouté ; 2 rayons plausibles de l'onglet « Rayons » sont proposés (question ouverte si
   Gemini est indisponible). Plusieurs articles inconnus : une question à la fois, les suivants en file d'attente.
2. Réponse, interprétée par le code (sans LLM) :
   - un rayon (ou « Divers ») → enregistré dans « Ingredients_Rayons » puis article ajouté : question posée une fois ;
   - « non », « annule » → rien n'est ajouté ni enregistré (file d'attente comprise) ;
   - autre chose → articles ajoutés et enregistrés sans rayon (à trier dans le classeur), la phrase reste à traiter.
"""
import re
import unicodedata
from typing import Dict, List, Literal, Optional, Sequence, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field

from app.connectors.sheets.meals_connector import MealsShoppingConnector
from app.connectors.sheets.models import WaitingListItem
from app.core.agent.tools.meals_models import RayonLearnedUndo, ShoppingAddedUndo
from app.core.llm.rayon_suggester import RayonSuggester

RAYON_QUESTION_KEY = "rayon_question"
DIVERS = "Divers"

RayonUndo = Union[RayonLearnedUndo, ShoppingAddedUndo]


class PendingRayonQuestion(BaseModel):
    """Question en attente dans le contexte de session."""
    model_config = ConfigDict(extra="forbid")

    article: str = Field(min_length=1)
    suggestions: List[str] = Field(default_factory=list)
    queue: List[str] = Field(default_factory=list, description="Autres articles inconnus, demandés ensuite.")


class RayonReply(BaseModel):
    kind: Literal["rayon", "cancel", "unrecognized"]
    rayon: Optional[str] = None


class RayonAnswer(BaseModel):
    spoken: str
    added: List[WaitingListItem] = Field(default_factory=list)
    undos: List[RayonUndo] = Field(default_factory=list)
    next_question: Optional[PendingRayonQuestion] = None
    consumed: bool = Field(description="False : réponse sans rapport, la phrase reste à traiter comme une demande.")


# --- Interprétation de la réponse ------------------------------------------------------------------------------

def _stem(word: str) -> str:
    return word[:-1] if len(word) > 3 and word[-1] in "sx" else word


def _tokens(text: str) -> List[str]:
    stripped = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", stripped.lower())]


def _words(text: str) -> frozenset:
    return frozenset(_tokens(text))


# Mots sans contenu tolérés autour d'un nom de rayon : « non, plutôt en hygiène », « range-le à l'épicerie ».
_FILLER = _words(
    "en au aux a à rayon le la les l de du des d dans et ou plutot plutôt non oui ok alors euh bien sur sûr merci "
    "stp svp mets met mettre range ranger laisse le-la ça ca c est je pense que il elle va"
)
_FIRST = _words("premier première premiere")
_SECOND = _words("deuxième deuxieme second seconde")
_CANCEL_WORDS = _words("non annule annuler laisse tomber oublie rien stop")
_CANCEL_ANCHORS = _words("non annule annuler tomber oublie rien stop")
_CANCEL_FILLER = _words("pas la peine merci c est bon ça ca")


def interpret_reply(reply: str, rayons: Sequence[str], suggestions: Sequence[str]) -> RayonReply:
    """Rayon reconnu uniquement si la réponse ne contient rien d'autre que ce rayon (et des mots sans contenu).

    Ainsi « ajoute du lait frais » n'est pas pris pour le rayon Frais : c'est une nouvelle demande.
    """
    words = _words(reply)
    content = words - _FILLER
    candidates = list(rayons) + ([DIVERS] if all(r.casefold() != DIVERS.casefold() for r in rayons) else [])

    if content:
        rayon = _closest([r for r in candidates if content <= _words(r)], suggestions)
        if rayon:
            return RayonReply(kind="rayon", rayon=rayon)
        if len(suggestions) >= 2:
            for ordinal, index in ((_FIRST, 0), (_SECOND, 1)):
                if content <= ordinal:
                    return RayonReply(kind="rayon", rayon=suggestions[index])

    if words & _CANCEL_ANCHORS and words <= _CANCEL_WORDS | _CANCEL_FILLER | _FILLER:
        return RayonReply(kind="cancel")
    return RayonReply(kind="unrecognized")


def rayon_cited(rayon: str, text: str) -> bool:
    """Le rayon est-il nommé dans les mots de l'utilisateur ? (« rayon entretien » cite « PQ + entretien »)."""
    return bool((_words(rayon) - _FILLER) & _words(text))


def _closest(matches: List[str], suggestions: Sequence[str]) -> Optional[str]:
    """Rayon au nom le plus court (« surgelé » → Surgelés plutôt que Légumes surgelés) ; à égalité, celui proposé
    dans la question ; sinon ambigu (None)."""
    if not matches:
        return None
    shortest = min(len(_words(r) - _FILLER) for r in matches)
    best = [r for r in matches if len(_words(r) - _FILLER) == shortest]
    if len(best) > 1:
        best = [r for r in best if r in suggestions]
    return best[0] if len(best) == 1 else None


# --- Question et réponse ---------------------------------------------------------------------------------------

def question_text(pending: PendingRayonQuestion) -> str:
    start = f"Je ne connais pas encore le rayon de « {pending.article} » :"
    if len(pending.suggestions) >= 2:
        return f"{start} je le range en {pending.suggestions[0]} ou en {pending.suggestions[1]} ?"
    return f"{start} dans quel rayon je le range ?"


def _join(names: Sequence[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} et {names[-1]}"


class RayonQuestions:
    def __init__(self, connector: MealsShoppingConnector, suggester: RayonSuggester) -> None:
        self.connector = connector
        self.suggester = suggester

    async def ask(self, articles: Sequence[str]) -> Tuple[PendingRayonQuestion, str]:
        names = list(dict.fromkeys(self.connector.clean_item_name(a) for a in articles))
        if not names:
            raise ValueError("Aucun article inconnu à soumettre à l'utilisateur.")
        suggestions = await self.suggester(names[0], self.connector.get_available_rayons())
        pending = PendingRayonQuestion(article=names[0], suggestions=suggestions, queue=names[1:])
        return pending, question_text(pending)

    async def answer(self, reply: str, pending: PendingRayonQuestion) -> RayonAnswer:
        articles = [pending.article, *pending.queue]
        result = interpret_reply(reply, self.connector.get_available_rayons(), pending.suggestions)

        if result.kind == "cancel":
            return RayonAnswer(spoken=f"D'accord, je n'ajoute pas {_join(articles)}.", consumed=True)
        if result.kind == "unrecognized":
            added, undos = learn_and_add(self.connector, {name: "" for name in articles})
            pronoun = "leur" if len(articles) > 1 else "son"
            return RayonAnswer(
                spoken=f"J'ai ajouté {_join(articles)}, {pronoun} rayon sera à trier plus tard dans votre sheet.",
                added=added, undos=undos, consumed=False,
            )

        added, undos = learn_and_add(self.connector, {pending.article: result.rayon})
        spoken = f"C'est noté, {pending.article} est ajouté au rayon {result.rayon}, je m'en souviendrai."
        next_question = None
        if pending.queue:
            next_question, question = await self.ask(pending.queue)
            spoken = f"{spoken} {question}"
        return RayonAnswer(spoken=spoken, added=added, undos=undos, next_question=next_question, consumed=True)


def learn_and_add(
    connector: MealsShoppingConnector, rayons: Dict[str, str],
) -> Tuple[List[WaitingListItem], List[RayonUndo]]:
    """Enregistre chaque rayon (vide = à trier) puis ajoute les articles, qui héritent du rayon appris."""
    undos: List[RayonUndo] = []
    for name, rayon in rayons.items():
        connector.learn_ingredient_rayon(name, rayon)
        undos.append(RayonLearnedUndo(ingredient=name, rayon=rayon))
    added, _ = connector.add_shopping_items(list(rayons))
    undos.append(ShoppingAddedUndo(items=[item.item for item in added]))
    return added, undos
