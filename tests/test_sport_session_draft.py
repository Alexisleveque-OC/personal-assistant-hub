"""Refonte UX (ROADMAP Étape 2, décision du 10/11) : « Dicte ta séance » — la dictée pré-remplit le formulaire Séance
sans rien enregistrer (route brouillon : transcription + 1 appel Gemini en sortie structurée)."""
import io
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.audio.stt_service import set_stt_service
from app.core.database import get_database_manager
from app.core.models import IntentType
from app.core.sport_session_draft import (
    DRAFT_SCHEMA,
    SessionDraftService,
    build_draft_prompt,
    parse_draft,
    set_session_draft_service,
)
from app.main import app

TODAY = date(2026, 11, 10)  # mardi


# ---------- Validation champ par champ ----------

def test_draft_keeps_the_valid_fields_and_drops_the_invalid_ones():
    draft, dropped = parse_draft({
        "date": "2026-11-09", "statut": "Réalisé", "type_seance": "Sortie Longue", "distance_km": 7.01,
        "duree_secondes": 2757, "denivele_d_plus": 29, "ressenti_rpe": 12, "meteo_note": 2,
        "douleur_intensite": 6, "douleur_zone": "genou droit", "remarques": "Grosse douleur au genou droit.",
        "inconnu": "x",
    })

    assert draft.model_dump(exclude_none=True) == {
        "date": date(2026, 11, 9), "statut": "Réalisé", "type_seance": "Sortie Longue", "distance_km": 7.01,
        "duree_secondes": 2757, "denivele_d_plus": 29, "meteo_note": 2,
        "douleur_intensite": 6, "douleur_zone": "genou droit", "remarques": "Grosse douleur au genou droit.",
    }
    assert dropped == ["ressenti_rpe"]


@pytest.mark.parametrize("old_type", ["Tempo", "Récup", "Seuil"])
def test_types_that_are_no_longer_proposed_are_left_empty(old_type):
    draft, dropped = parse_draft({"type_seance": old_type})
    assert draft.type_seance is None and dropped == ["type_seance"]


def test_schema_and_prompt_give_gemini_today_and_the_proposed_types():
    assert DRAFT_SCHEMA["properties"]["type_seance"]["enum"] == [
        "EF", "Course", "Sortie Longue", "Vitesse", "Fractionné", "Renforcement",
    ]
    prompt = build_draft_prompt("hier sortie longue de 7 km", TODAY)
    assert "mardi 10/11/2026" in prompt and "hier sortie longue de 7 km" in prompt
    assert "n'invente" in prompt.lower()


@pytest.mark.asyncio
async def test_service_asks_gemini_once_and_returns_the_draft():
    caller = AsyncMock(return_value={"type_seance": "Course", "distance_km": 5})
    service = SessionDraftService(llm_caller=caller, today=lambda: TODAY)

    result = await service.draft("5 km de course ce matin")

    caller.assert_awaited_once()
    assert result.draft.type_seance == "Course" and result.draft.distance_km == 5
    assert result.dropped == []


# ---------- Route ----------

class FakeDraftService:
    def __init__(self, raw=None, error=None):
        self.raw, self.error, self.texts = raw or {}, error, []

    async def draft(self, text):
        self.texts.append(text)
        if self.error:
            raise self.error
        draft, dropped = parse_draft(self.raw)
        return MagicMock(draft=draft, dropped=dropped)


@pytest.fixture
def client(isolate_sqlite_database):
    yield TestClient(app)
    set_session_draft_service(None)
    set_stt_service(None)


def test_route_drafts_from_text_without_saving_or_logging_anything(client):
    fake = FakeDraftService({"type_seance": "Course", "distance_km": 5})
    set_session_draft_service(fake)
    db = get_database_manager()

    res = client.post("/api/v1/sport/session/draft", data={"text": "5 km de course ce matin"})

    assert res.status_code == 200, res.text
    assert res.json() == {
        "transcription": "5 km de course ce matin",
        "draft": {"type_seance": "Course", "distance_km": 5.0},
        "dropped": [],
    }
    assert db.get_sport_sessions() == []
    assert db.get_conversation_logs()["total"] == 0


def test_route_transcribes_the_audio_first(client):
    fake = FakeDraftService({"type_seance": "Vitesse"})
    set_session_draft_service(fake)
    parsed = MagicMock(intent=IntentType.UNKNOWN, parameters={}, confidence=0.0, conversational_reply=None, raw_query="")
    stt = MagicMock()
    stt.process_audio = AsyncMock(return_value=("séance de vitesse jeudi", parsed))
    set_stt_service(stt)

    res = client.post(
        "/api/v1/sport/session/draft",
        files={"audio_file": ("dictee.webm", io.BytesIO(b"AUDIO"), "audio/webm")},
    )

    assert res.status_code == 200, res.text
    assert res.json()["transcription"] == "séance de vitesse jeudi"
    assert fake.texts == ["séance de vitesse jeudi"]


def test_route_needs_text_or_audio(client):
    set_session_draft_service(FakeDraftService())
    res = client.post("/api/v1/sport/session/draft", data={})
    assert res.status_code == 422
    assert "texte ou audio" in res.json()["detail"]


def test_route_explains_when_gemini_is_unavailable(client):
    from app.core.sport_session_draft import SessionDraftUnavailableError
    set_session_draft_service(FakeDraftService(error=SessionDraftUnavailableError("tous les modèles ont échoué")))

    res = client.post("/api/v1/sport/session/draft", data={"text": "5 km"})

    assert res.status_code == 503
    assert "remplis le formulaire à la main" in res.json()["detail"]
