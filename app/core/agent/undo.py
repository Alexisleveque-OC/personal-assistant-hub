"""Annulation fiable des actions de l'agent : journal SQLite par session et restauration « tout ou rien »."""
from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, Field, TypeAdapter

from app.core.agent.tools.meals_models import (
    MealUndo,
    RayonLearnedUndo,
    ShoppingAddedUndo,
    ShoppingCheckedUndo,
    ShoppingRemovedUndo,
)
from app.core.agent.tools.meals_tools import MealsTools
from app.core.agent.tools.sport_models import UndoSnapshot
from app.core.agent.tools.sport_tools import SportToolError, SportTools
from app.core.agent.tools.tool_error import ToolError
from app.core.database import DatabaseManager


class NoteUndo(BaseModel):
    kind: Literal["note"] = "note"
    note_id: int


AgentUndo = Annotated[
    Union[UndoSnapshot, NoteUndo, ShoppingAddedUndo, ShoppingCheckedUndo, ShoppingRemovedUndo, MealUndo, RayonLearnedUndo],
    Field(discriminator="kind"),
]
_MEALS_UNDOS = (ShoppingAddedUndo, ShoppingCheckedUndo, ShoppingRemovedUndo, MealUndo, RayonLearnedUndo)
_UNDOS_ADAPTER = TypeAdapter(List[AgentUndo])


class UndoError(SportToolError):
    """Annulation impossible (rien à annuler, données modifiées depuis…) : message renvoyé tel quel."""


class UndoBatch(BaseModel):
    id: int
    undos: List[AgentUndo]


class UndoOutcome(BaseModel):
    batch_id: int
    restored: List[str]
    sport_session_ids: List[int]


class UndoJournal:
    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def record(self, session_id: str, undos: List[AgentUndo]) -> Optional[int]:
        if not undos:
            return None
        return self.db.add_agent_undo_batch(session_id, _UNDOS_ADAPTER.dump_json(undos).decode("utf-8"))

    def last(self, session_id: str) -> Optional[UndoBatch]:
        row = self.db.get_last_agent_undo_batch(session_id)
        if row is None:
            return None
        return UndoBatch(id=row["id"], undos=_UNDOS_ADAPTER.validate_json(row["undos_json"]))

    def mark_undone(self, batch_id: int) -> None:
        if not self.db.mark_agent_undo_batch_undone(batch_id):
            raise UndoError(f"Le lot d'annulation {batch_id} est introuvable ou déjà annulé.")


class UndoService:
    def __init__(
        self, sport_tools: SportTools, db: DatabaseManager, journal: UndoJournal, meals_tools: Optional[MealsTools] = None,
    ) -> None:
        self.sport_tools = sport_tools
        self.db = db
        self.journal = journal
        self.meals_tools = meals_tools

    def undo_last(self, session_id: str) -> UndoOutcome:
        batch = self.journal.last(session_id)
        if batch is None:
            raise UndoError("Aucune action récente de l'assistant à annuler dans cette conversation.")

        steps = list(reversed(batch.undos))
        # Tout ou rien : chaque cible est vérifiée avant la moindre restauration. Seule sa dernière mutation
        # doit correspondre à l'état actuel ; les précédentes s'enchaînent et sont revérifiées pas à pas.
        latest_per_target = {target: index for index, undo in enumerate(batch.undos) for target in self._targets(undo)}
        for index, undo in enumerate(batch.undos):
            owned = {target for target in self._targets(undo) if latest_per_target[target] == index}
            if owned:
                self._check(undo, owned)
        restored = [self._apply(undo) for undo in steps]
        self.journal.mark_undone(batch.id)
        sport_ids = list(dict.fromkeys(u.session_id for u in steps if isinstance(u, UndoSnapshot)))
        return UndoOutcome(batch_id=batch.id, restored=restored, sport_session_ids=sport_ids)

    @staticmethod
    def _targets(undo: AgentUndo) -> List[tuple]:
        if isinstance(undo, NoteUndo):
            return [("note", undo.note_id)]
        if isinstance(undo, UndoSnapshot):
            return [("sport_session", undo.session_id)]
        return MealsTools.undo_targets(undo)

    def _meals(self) -> MealsTools:
        if self.meals_tools is None:
            raise UndoError("Annulation impossible : le classeur Repas & Courses est indisponible.")
        return self.meals_tools

    def _check(self, undo: AgentUndo, targets: set) -> None:
        if isinstance(undo, _MEALS_UNDOS):
            try:
                self._meals().check_undo(undo, only=targets)
            except ToolError as exc:
                raise UndoError(str(exc)) from exc
            return
        if isinstance(undo, NoteUndo):
            if self.db.get_note(undo.note_id) is None:
                raise UndoError(f"Annulation impossible : la note {undo.note_id} n'existe plus.")
            return
        try:
            self.sport_tools.check_sport_undo(undo)
        except SportToolError as exc:
            raise UndoError(str(exc)) from exc

    def _apply(self, undo: AgentUndo) -> str:
        if isinstance(undo, _MEALS_UNDOS):
            return self._meals().apply_undo(undo)
        if isinstance(undo, NoteUndo):
            content = self.db.get_note(undo.note_id)["content"]
            self.db.delete_note(undo.note_id)
            return f"note « {content} » supprimée"
        label = f"séance {undo.after.type_seance} du {undo.after.date[8:10]}/{undo.after.date[5:7]}"
        self.sport_tools.undo_sport_mutation(undo)
        return f"{label} supprimée" if undo.action == "created" else f"{label} restaurée"

