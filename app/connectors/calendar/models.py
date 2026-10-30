"""Modèles Pydantic du connecteur Google Agenda."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CalendarEvent(BaseModel):
    """Occurrence d'événement, heures exprimées à Paris.

    Journée entière : `debut` à minuit du premier jour, `fin` à minuit du lendemain du dernier jour (exclusive).
    """
    titre: str
    agenda: str
    journee_entiere: bool
    debut: datetime
    fin: datetime
    lieu: Optional[str] = None
