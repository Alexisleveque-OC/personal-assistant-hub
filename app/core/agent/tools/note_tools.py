"""Outil agent de prise de note dans le second cerveau."""
from typing import List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from app.core.agent.agent_service import ConversationTurn
from app.core.agent.tool_registry import AgentTool
from app.core.agent.tools.sport_models import StrictArgs
from app.core.agent.undo import NoteUndo
from app.core.database import DatabaseManager
from app.core.models import NoteCategory


class SaveNoteArgs(StrictArgs):
    content: str = Field(
        min_length=1,
        pattern=r"\S",
        description="Contenu autonome et compréhensible plus tard, rédigé en français (reformule le contexte si besoin).",
    )
    category: NoteCategory = Field(NoteCategory.THOUGHT, description="Catégorie de la note.")
    tags: List[str] = Field(default_factory=list)
    inclure_dernier_echange: bool = Field(
        False,
        description=(
            "true si l'utilisateur renvoie aux échanges précédents (« note ces derniers échanges », « note ça ») : "
            "l'application ajoute le texte exact du dernier échange sous ton résumé."
        ),
    )


class NoteSaved(BaseModel):
    note_id: int
    category: NoteCategory
    content: str
    undos: List[NoteUndo]


def _last_exchange(history: Sequence[ConversationTurn]) -> Optional[Tuple[str, str]]:
    """Dernière question de l'utilisateur et la réponse de l'assistant qui la suit."""
    for index in range(len(history) - 2, -1, -1):
        if history[index].role == "user" and history[index + 1].role == "assistant":
            return history[index].text, history[index + 1].text
    return None


def note_tool_definitions(db: DatabaseManager, history: Sequence[ConversationTurn] = ()) -> List[AgentTool]:
    def save_note(args: SaveNoteArgs) -> NoteSaved:
        content = args.content.strip()
        exchange = _last_exchange(history) if args.inclure_dernier_echange else None
        if exchange:
            # Extrait exact : la note reste fidèle même si le résumé du modèle est vague.
            content += f"\n\n— Dernier échange —\nToi : {exchange[0]}\nOtis : {exchange[1]}"
        note_id = db.add_note(category=args.category.value, content=content, tags=args.tags)
        return NoteSaved(note_id=note_id, category=args.category, content=content, undos=[NoteUndo(note_id=note_id)])

    return [AgentTool(
        name="save_note",
        description=(
            "Enregistre une note dans le second cerveau (idée, bug, tâche, préférence, réflexion). "
            "Si l'utilisateur renvoie aux échanges précédents, résume-les précisément et passe "
            "inclure_dernier_echange=true."
        ),
        args_model=SaveNoteArgs,
        handler=save_note,
    )]
