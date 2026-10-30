"""Contrats Pydantic des outils Agenda de l'agent : arguments stricts et vues renvoyées au modèle."""
from datetime import date as dt_date
from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.agent.tools.sport_models import StrictArgs


class GetAgendaArgs(StrictArgs):
    date_debut: dt_date
    date_fin: Optional[dt_date] = Field(None, description="Dernier jour inclus (par défaut : date_debut). 14 jours maximum.")


class AgendaEvent(BaseModel):
    titre: str
    journee_entiere: bool
    heure_debut: Optional[str] = Field(None, description="HH:MM, absente pour un événement sur la journée entière.")
    heure_fin: Optional[str] = None
    lieu: Optional[str] = None
    agenda: str


class AgendaDay(BaseModel):
    date: dt_date
    jour: str
    evenements: List[AgendaEvent]


class AgendaView(BaseModel):
    jours: List[AgendaDay]
