"""Modèles Pydantic du connecteur Google Tasks."""
from datetime import date
from typing import Optional

from pydantic import BaseModel


class TaskItem(BaseModel):
    """Tâche non terminée. `echeance` : jour seulement (Google Tasks ne conserve pas l'heure d'échéance)."""
    id: str
    titre: str
    echeance: Optional[date] = None
    notes: Optional[str] = None
