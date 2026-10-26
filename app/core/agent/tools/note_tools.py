"""Outil agent de prise de note dans le second cerveau."""
from typing import List

from pydantic import BaseModel, Field

from app.core.agent.tool_registry import AgentTool
from app.core.agent.tools.sport_models import StrictArgs
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


class NoteSaved(BaseModel):
    note_id: int
    category: NoteCategory
    content: str


def note_tool_definitions(db: DatabaseManager) -> List[AgentTool]:
    def save_note(args: SaveNoteArgs) -> NoteSaved:
        content = args.content.strip()
        note_id = db.add_note(category=args.category.value, content=content, tags=args.tags)
        return NoteSaved(note_id=note_id, category=args.category, content=content)

    return [AgentTool(
        name="save_note",
        description=(
            "Enregistre une note dans le second cerveau (idée, bug, tâche, préférence, réflexion). "
            "Si l'utilisateur renvoie aux échanges précédents, résume-les dans la note."
        ),
        args_model=SaveNoteArgs,
        handler=save_note,
    )]
