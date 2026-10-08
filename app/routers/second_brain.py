"""Router FastAPI pour le Second Cerveau compartimenté (CRUD de notes et statistiques)."""
import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import verify_api_key
from app.core.dependencies import get_database_manager
from app.core.models import (
    NoteCategory,
    SecondBrainNoteItem,
    SecondBrainNotesListResponse,
    NoteCreate,
    NoteUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/second-brain",
    tags=["Second Brain"],
    dependencies=[Depends(verify_api_key)],
)


@router.get(
    "/notes",
    response_model=SecondBrainNotesListResponse,
    summary="Récupération paginée et filtrée des notes du second cerveau",
)
async def list_notes_endpoint(
    category: Optional[str] = None,
    status: Optional[str] = "active",
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """Retourne les notes filtrées par segment (dev_idea, bug_report, etc.), statut et recherche."""
    db = get_database_manager()
    return db.get_notes(
        category=category,
        status=status,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/notes",
    response_model=SecondBrainNoteItem,
    status_code=status.HTTP_201_CREATED,
    summary="Création manuelle d'une note",
)
async def create_note_endpoint(payload: NoteCreate):
    """Enregistre une nouvelle note dans le second cerveau."""
    db = get_database_manager()
    cat = payload.category or NoteCategory.THOUGHT.value
    note_id = db.add_note(
        category=cat,
        content=payload.content,
        tags=payload.tags or [],
    )
    created = db.get_note(note_id)
    if not created:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Impossible de récupérer la note créée.",
        )
    return created


@router.get(
    "/notes/{note_id}",
    response_model=SecondBrainNoteItem,
    summary="Détail d'une note par son ID",
)
async def get_note_endpoint(note_id: int):
    """Récupère une note spécifique."""
    db = get_database_manager()
    note = db.get_note(note_id)
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note {note_id} introuvable.",
        )
    return note


@router.patch(
    "/notes/{note_id}",
    response_model=SecondBrainNoteItem,
    summary="Mise à jour partielle d'une note",
)
async def update_note_endpoint(note_id: int, payload: NoteUpdate):
    """Met à jour le contenu, le segment ou le statut (ex: active -> done) d'une note."""
    db = get_database_manager()
    existing = db.get_note(note_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note {note_id} introuvable.",
        )

    updated = db.update_note(
        note_id=note_id,
        category=payload.category,
        content=payload.content,
        status=payload.status,
        tags=payload.tags,
    )

    if not updated and not payload.model_dump(exclude_unset=True):
        pass

    return db.get_note(note_id)


@router.delete(
    "/notes/{note_id}",
    summary="Suppression d'une note",
)
async def delete_note_endpoint(note_id: int):
    """Supprime définitivement une note."""
    db = get_database_manager()
    existing = db.get_note(note_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note {note_id} introuvable.",
        )

    deleted = db.delete_note(note_id)
    return {"success": deleted, "note_id": note_id}


@router.get(
    "/stats",
    summary="Statistiques par segment du second cerveau",
)
async def get_notes_stats_endpoint() -> Dict[str, int]:
    """Retourne le nombre de notes actives par segment (dev_idea, bug_report, etc.)."""
    db = get_database_manager()
    return db.get_notes_stats()
