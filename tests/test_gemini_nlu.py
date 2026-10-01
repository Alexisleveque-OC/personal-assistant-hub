"""Tests unitaires pour le moteur d'intentions LLM Gemini (Phase Rouge TDD)."""
import pytest
from unittest.mock import AsyncMock, patch
import httpx

from app.core.models import IntentType, ParsedIntent
from app.core.llm.gemini_client import GeminiClient
from app.core.llm.nlu_service import GeminiNLUService, LLMNLUResponse


def test_llm_nlu_response_pydantic_validation():
    """Valide le modèle Pydantic LLMNLUResponse servant de schéma de sortie structurée."""
    raw_payload = {
        "intent": "add_shopping_item",
        "confidence": 0.98,
        "parameters": {"item": "papier cuisson"},
        "conversational_reply": "Je l'ajoute à votre liste de courses.",
    }
    resp = LLMNLUResponse.model_validate(raw_payload)
    assert resp.intent == IntentType.ADD_SHOPPING_ITEM
    assert resp.confidence == 0.98
    assert resp.parameters["item"] == "papier cuisson"
    assert resp.conversational_reply == "Je l'ajoute à votre liste de courses."


@pytest.mark.asyncio
async def test_llm_nlu_service_parse_mocked_success():
    """Vérifie l'analyse d'une phrase avec réponse structurée simulée de Gemini."""
    mock_gemini_api_resp = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": (
                                '{"intent": "add_shopping_item", "confidence": 0.99, '
                                '"parameters": {"item": "papier sulfurisé"}, '
                                '"conversational_reply": "Noté !"}'
                            )
                        }
                    ]
                }
            }
        ]
    }

    client = GeminiClient(api_key="fake-key", model="gemini-2.0-flash")
    nlu_service = GeminiNLUService(gemini_client=client)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: mock_gemini_api_resp
        mock_resp.raise_for_status = lambda: None
        mock_post.return_value = mock_resp

        parsed: ParsedIntent = await nlu_service.parse("Met du papier sulfurisé sur ma liste")

        assert parsed.intent == IntentType.ADD_SHOPPING_ITEM
        assert parsed.parameters["item"] == "papier sulfurisé"
        assert parsed.raw_query == "Met du papier sulfurisé sur ma liste"
        assert mock_post.call_count == 1
        assert client.get_usage_stats()["daily_requests"] == 1


@pytest.mark.asyncio
async def test_llm_nlu_service_fallback_when_quota_exceeded():
    """Si le quota quotidien est dépassé, bascule automatiquement sur le parseur local déterministe."""
    client = GeminiClient(api_key="fake-key", max_daily_requests=0)
    assert client.is_daily_quota_exceeded() is True

    nlu_service = GeminiNLUService(gemini_client=client)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # La requête ne doit pas appeler l'API Google
        parsed = await nlu_service.parse("Ajoute du café bio à la liste de courses")
        assert parsed.intent == IntentType.ADD_SHOPPING_ITEM
        assert parsed.parameters["item"] == "café bio"
        assert mock_post.call_count == 0


@pytest.mark.asyncio
async def test_llm_nlu_service_fallback_on_api_error():
    """En cas d'erreur de l'API Gemini (ex: 429 ou timeout), bascule sur le parseur local sans lever d'exception."""
    client = GeminiClient(api_key="fake-key", model="gemini-2.0-flash")
    nlu_service = GeminiNLUService(gemini_client=client)

    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectTimeout("Timeout")):
        parsed = await nlu_service.parse("Qu'est-ce qu'on mange ce soir ?")
        assert parsed.intent == IntentType.GET_MEAL_PLAN
        assert parsed.parameters.get("period") == "soir"


@pytest.mark.asyncio
async def test_llm_nlu_service_context_anaphora():
    """Vérifie que le contexte de session est transmis pour résoudre l'anaphore ('ses ingrédients')."""
    mock_gemini_api_resp = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": (
                                '{"intent": "add_recipe_ingredients", "confidence": 0.95, '
                                '"parameters": {"recipe": "lasagnes maison"}, '
                                '"conversational_reply": "Ingrédients des lasagnes ajoutés."}'
                            )
                        }
                    ]
                }
            }
        ]
    }

    client = GeminiClient(api_key="fake-key", model="gemini-2.0-flash")
    nlu_service = GeminiNLUService(gemini_client=client)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: mock_gemini_api_resp
        mock_resp.raise_for_status = lambda: None
        mock_post.return_value = mock_resp

        context = {"last_recipe": "lasagnes maison"}
        parsed = await nlu_service.parse("Ajoute ses ingrédients", context=context)

        assert parsed.intent == IntentType.ADD_RECIPE_INGREDIENTS
        assert parsed.parameters["recipe"] == "lasagnes maison"


@pytest.mark.asyncio
async def test_live_gemini_nlu_real_query():
    """Test réel d'extraction d'intention avec la vraie clé Gemini configurée."""
    from app.config import settings as app_settings
    if not app_settings.gemini_api_key or app_settings.gemini_api_key.startswith("fake"):
        pytest.skip("Aucune clé GEMINI_API_KEY réelle configurée.")

    client = GeminiClient(api_key=app_settings.gemini_api_key, model="auto")
    nlu_service = GeminiNLUService(gemini_client=client)

    # Formulation orale naturelle familière non couverte par les regex classiques
    query = "Dis-moi un peu ce qu'on a prévu comme bon plat pour ce soir"
    parsed = await nlu_service.parse(query)

    assert parsed.intent == IntentType.GET_MEAL_PLAN
    assert parsed.parameters.get("period") == "soir" or "soir" in str(parsed.parameters)
    print(f"\n[LIVE NLU] Query: '{query}' -> Intent: {parsed.intent}, Params: {parsed.parameters}")
