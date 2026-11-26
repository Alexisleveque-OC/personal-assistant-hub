"""Phase 10, étape 8 (1/4) : extraction des captures Swile (Gemini Vision simulé, jamais appelé).

Formats relevés sur les vraies captures du 26/11 : « Derniers paiements » en dates complètes (« mercredi 25 nov. 2026,
17:35 »), accueil « Avantages » en dates relatives (« Hier, 17:35 », « lundi, 12:52 », « 14 novembre, 11:10 ») et
solde « Titres-resto 95,64 € ». Date de référence = jour de l'import ; une ligne illisible donne None (ignorée et
signalée, décision du 26/11), jamais la date du jour par défaut.
"""
import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.swile_import.dates import parse_swile_date
from app.core.swile_import.models import SwileCapture
from app.core.vision.swile_vision_service import GEMINI_SWILE_VISION_SCHEMA, SwileVisionService
from app.core.vision.sport_vision_service import VisionServiceUnavailableError

THURSDAY = date(2026, 11, 26)


@pytest.mark.parametrize("raw, expected", [
    ("mercredi 25 nov. 2026, 17:35", date(2026, 11, 25)),
    ("jeudi 29 oct. 2026, 17:43", date(2026, 10, 29)),
    # Piège : « dimanche 1 » tombe aussi un dimanche en novembre 2026 ; le mois écrit l'emporte.
    ("dimanche 1 mars 2026, 10:00", date(2026, 3, 1)),
    ("Hier, 17:35", date(2026, 11, 25)),
    ("Aujourd'hui, 09:12", THURSDAY),
    ("Aujourd’hui, 09:12", THURSDAY),
    ("Avant-hier, 08:00", date(2026, 11, 24)),
    ("lundi, 12:52", date(2026, 11, 23)),
    ("samedi, 10:27", date(2026, 11, 21)),
    # Swile écrit « Aujourd'hui » pour le jour même : le même jour de semaine est celui d'il y a 7 jours.
    ("jeudi, 08:00", date(2026, 11, 19)),
    ("14 novembre, 11:10", date(2026, 11, 14)),
    ("28 décembre, 10:00", date(2025, 12, 28)),
    ("1 janv. 2026", date(2026, 1, 1)),
])
def test_swile_dates_are_resolved_from_the_import_day(raw, expected):
    assert parse_swile_date(raw, reference_date=THURSDAY) == expected


@pytest.mark.parametrize("raw", ["", None, "n'importe quoi", "30 févr. 2026", "vendredi 27 nov. 2026, 10:00", "17:35"])
def test_unreadable_or_future_swile_dates_give_none(raw):
    assert parse_swile_date(raw, reference_date=THURSDAY) is None


def _client(api_key: str = "fake_key") -> MagicMock:
    fake = MagicMock()
    fake.api_key = api_key
    fake.premium_candidate_models = AsyncMock(return_value=["gemini-test-flash"])
    return fake


def _gemini_reply(payload: dict) -> MagicMock:
    response = MagicMock(status_code=200)
    response.json.return_value = {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]}
    return response


@pytest.mark.asyncio
async def test_vision_reply_becomes_a_typed_capture():
    payload = {
        "is_swile": True,
        "solde": 95.64,
        "lignes": [
            {"marchand": "Intermarche", "date_texte": "Hier, 17:35", "montant": -12.81},
            {"marchand": "Crédit titres-resto", "date_texte": "vendredi 6 nov. 2026, 04:13", "montant": 242.0},
        ],
    }
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as post:
        post.return_value = _gemini_reply(payload)
        capture = await SwileVisionService(gemini_client=_client()).analyze_screenshot(b"img", "image/jpeg")

    assert isinstance(capture, SwileCapture)
    assert capture.is_swile and capture.solde == 95.64
    assert [(l.marchand, l.date_texte, l.montant) for l in capture.lignes] == [
        ("Intermarche", "Hier, 17:35", -12.81), ("Crédit titres-resto", "vendredi 6 nov. 2026, 04:13", 242.0),
    ]
    sent = post.call_args.kwargs["json"]
    assert sent["generationConfig"]["responseSchema"] == GEMINI_SWILE_VISION_SCHEMA
    assert post.call_args.kwargs["headers"] == {"x-goog-api-key": "fake_key"}  # jamais la clé dans l'URL


@pytest.mark.asyncio
async def test_missing_api_key_is_an_explicit_error():
    with pytest.raises(VisionServiceUnavailableError, match="GEMINI_API_KEY"):
        await SwileVisionService(gemini_client=_client(api_key="")).analyze_screenshot(b"img", "image/jpeg")


@pytest.mark.asyncio
async def test_every_model_failing_is_an_explicit_error():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as post:
        post.return_value = MagicMock(status_code=500, text="boom")
        with pytest.raises(VisionServiceUnavailableError, match=r"gemini-test-flash \(500\)"):
            await SwileVisionService(gemini_client=_client()).analyze_screenshot(b"img", "image/jpeg")


def test_prompt_states_what_to_ignore_and_the_sign_convention():
    prompt = SwileVisionService(gemini_client=_client()).build_prompt().lower()
    assert "dépensez jusqu" in prompt  # plafond du jour : pas le solde
    assert "coupée" in prompt  # ligne partiellement visible : ignorée
    assert "positif" in prompt and "négatif" in prompt


def test_schema_allows_a_missing_balance_and_requires_the_lines():
    props = GEMINI_SWILE_VISION_SCHEMA["properties"]
    assert props["solde"].get("nullable") is True
    assert {"is_swile", "lignes", "solde"} <= set(GEMINI_SWILE_VISION_SCHEMA["required"])
    line = props["lignes"]["items"]
    assert set(line["required"]) == {"marchand", "date_texte", "montant"}
