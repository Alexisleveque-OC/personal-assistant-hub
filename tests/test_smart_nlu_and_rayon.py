"""Tests de l'intégration du cerveau LLM Gemini dans /api/v1/interact, de la déduction intelligente de rayon et des réponses réfléchies (Étape 5 - TDD)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app, set_meals_connector
from app.core.models import IntentType, ParsedIntent
from app.connectors.sheets.models import WaitingListItem

client = TestClient(app)


def test_interact_understands_natural_phrasing_needs_to_buy():
    """L'assistant comprend les formulations naturelles comme 'j'ai besoin d'acheter des mandarines'."""
    mock_connector = MagicMock()
    mock_connector.resolve_rayon.return_value = ("Fruits & Légumes", None)
    mock_connector.add_shopping_item.return_value = (
        WaitingListItem(item="Mandarines", rayon="Fruits & Légumes"),
        None,
    )
    set_meals_connector(mock_connector)

    # Simulation du retour NLU intelligent de Gemini
    smart_parsed = ParsedIntent(
        intent=IntentType.ADD_SHOPPING_ITEM,
        confidence=0.98,
        parameters={"item": "mandarines", "rayon": "Fruits & Légumes"},
        raw_query="j'ai besoin d'acheter des mandarines",
    )

    with patch("app.main.get_nlu_service") as mock_get_nlu:
        mock_nlu = AsyncMock()
        mock_nlu.parse.return_value = smart_parsed
        mock_get_nlu.return_value = mock_nlu

        res = client.post(
            "/api/v1/interact",
            json={"query": "j'ai besoin d'acheter des mandarines"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "mandarines" in data["spoken_response"].lower()
        mock_nlu.parse.assert_called_once()

    set_meals_connector(None)


def test_interact_unknown_intent_uses_smart_conversational_reply():
    """Quand une requête est floue ou réflexive ('j'ai faim'), l'assistant réfléchit et utilise la conversational_reply."""
    smart_parsed = ParsedIntent(
        intent=IntentType.UNKNOWN,
        confidence=0.95,
        parameters={},
        raw_query="j'ai faim",
        conversational_reply="Je comprends ! Tu veux qu'on regarde le planning des repas ou que je te suggère une recette rapide ?",
    )

    with patch("app.main.get_nlu_service") as mock_get_nlu:
        mock_nlu = AsyncMock()
        mock_nlu.parse.return_value = smart_parsed
        mock_get_nlu.return_value = mock_nlu

        res = client.post(
            "/api/v1/interact",
            json={"query": "j'ai faim"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["spoken_response"] == "Je comprends ! Tu veux qu'on regarde le planning des repas ou que je te suggère une recette rapide ?"
        assert "reformuler" not in data["spoken_response"].lower()


def test_interact_ambiguous_item_triggers_targeted_clarification():
    """Pour un produit ambigu (ex: papier cuisson), l'assistant propose les options ciblées."""
    mock_connector = MagicMock()
    mock_connector.resolve_rayon.return_value = ("Divers", "Article non répertorié")
    mock_connector.get_available_rayons.return_value = ["PQ + entretien", "Épicerie", "Fruits"]
    set_meals_connector(mock_connector)

    smart_parsed = ParsedIntent(
        intent=IntentType.ADD_SHOPPING_ITEM,
        confidence=0.95,
        parameters={
            "item": "papier cuisson",
            "rayon": "Épicerie",
            "is_ambiguous": True,
            "suggested_options": ["PQ + entretien", "Épicerie"],
        },
        raw_query="ajoute du papier cuisson",
        conversational_reply="Le papier cuisson peut aller au rayon Entretien ou Épicerie. Où préfères-tu que je le range ?",
    )

    with patch("app.main.get_nlu_service") as mock_get_nlu:
        mock_nlu = AsyncMock()
        mock_nlu.parse.return_value = smart_parsed
        mock_get_nlu.return_value = mock_nlu

        res = client.post(
            "/api/v1/interact",
            json={"query": "ajoute du papier cuisson"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "entretien" in data["spoken_response"].lower()
        assert "épicerie" in data["spoken_response"].lower()
        assert data.get("data", {}).get("pending_action", {}).get("type") == "clarify_shopping_rayon"

    set_meals_connector(None)


@pytest.mark.asyncio
async def test_gemini_smart_rayon_deduction_for_unknown_item():
    """Gemini déduit intelligemment le rayon d'un article absent du catalogue (ex: mandarines -> Fruits & Légumes)."""
    from app.core.llm.nlu_service import GeminiNLUService
    from app.core.llm.gemini_client import GeminiClient

    client_llm = GeminiClient(api_key="fake-key", model="gemini-3.5-flash-lite")
    nlu_service = GeminiNLUService(gemini_client=client_llm)

    available_rayons = [
        "Fruits & Légumes",
        "Boucherie",
        "Frais",
        "Épicerie",
        "Surgelés",
        "Entretien",
        "Hygiène",
        "Boisson",
        "Divers",
    ]

    mock_gemini_resp = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": (
                                '{"intent": "add_shopping_item", "confidence": 0.99, '
                                '"parameters": {"item": "mandarines", "rayon": "Fruits & Légumes", "is_ambiguous": false}, '
                                '"conversational_reply": "J\'ai ajouté les mandarines au rayon Fruits & Légumes."}'
                            )
                        }
                    ]
                }
            }
        ]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: mock_gemini_resp
        mock_resp.raise_for_status = lambda: None
        mock_post.return_value = mock_resp

        parsed = await nlu_service.parse(
            "j'ai besoin d'acheter des mandarines",
            context={"available_rayons": available_rayons},
        )

        assert parsed.intent == IntentType.ADD_SHOPPING_ITEM
        assert parsed.parameters.get("item") == "mandarines"
        assert parsed.parameters.get("rayon") == "Fruits & Légumes"
        assert parsed.parameters.get("is_ambiguous") is False
        assert parsed.conversational_reply is not None


@pytest.mark.asyncio
async def test_gemini_client_rate_limit_cooldown_and_fallback():
    """Vérifie que la détection d'un 429 met en pause le modèle et bascule immédiatement sur le suivant."""
    from app.core.llm.gemini_client import GeminiClient
    from app.core.llm.nlu_service import GeminiNLUService

    client_llm = GeminiClient(api_key="fake-key", model="auto")
    client_llm._candidate_models = ["model-busy-429", "model-ok"]
    client_llm._resolved_model = "model-busy-429"

    nlu_service = GeminiNLUService(gemini_client=client_llm)

    mock_resp_429 = AsyncMock()
    mock_resp_429.status_code = 429

    mock_resp_200 = AsyncMock()
    mock_resp_200.status_code = 200
    mock_resp_200.json = lambda: {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": '{"intent": "small_talk", "confidence": 1.0, "parameters": {}, "conversational_reply": "Bonjour Alexis !"}'
                        }
                    ]
                }
            }
        ]
    }
    mock_resp_200.raise_for_status = lambda: None

    with patch("httpx.AsyncClient.post", side_effect=[mock_resp_429, mock_resp_200]):
        parsed = await nlu_service.parse("bonjour")
        assert parsed.intent == IntentType.SMALL_TALK
        assert parsed.conversational_reply == "Bonjour Alexis !"
        # Le modèle 429 a été marqué en cooldown
        assert "model-busy-429" in client_llm._temporarily_unavailable_models


def test_interact_maintains_conversation_history_across_turns():
    """Vérifie que l'historique conversationnel est conservé et alimenté entre les tours de parole."""
    session_id = "test_history_retention_session"

    r1 = client.post(
        "/api/v1/interact",
        json={"query": "Bonjour", "session_id": session_id},
    )
    assert r1.status_code == 200
    assert r1.json()["success"] is True

    # Deuxième tour confirmant dans le fil
    r2 = client.post(
        "/api/v1/interact",
        json={"query": "oui", "session_id": session_id},
    )
    assert r2.status_code == 200
    assert r2.json()["spoken_response"] != ""


def test_interact_handles_relative_target_date_today_and_tonight():
    """Vérifie que target_date='today' extrait par le LLM ne provoque pas d'erreur de parsing date."""
    from app.connectors.sheets.models import DayMealPlan
    from datetime import date

    mock_connector = MagicMock()
    mock_connector.get_meal_plan.return_value = DayMealPlan(
        date_str=date.today().strftime("%d/%m/%Y"),
        day_name="Vendredi",
        lunch="Salade César",
        dinner="Lasagnes maison",
    )
    set_meals_connector(mock_connector)

    smart_parsed = ParsedIntent(
        intent=IntentType.GET_MEAL_PLAN,
        confidence=0.95,
        parameters={"period": "soir", "target_date": "today"},
        raw_query="Salut! qu'est qu'on a prévu de bon pour ce soir?",
    )

    with patch("app.main.get_nlu_service") as mock_get_nlu:
        mock_nlu = AsyncMock()
        mock_nlu.parse.return_value = smart_parsed
        mock_get_nlu.return_value = mock_nlu

        res = client.post(
            "/api/v1/interact",
            json={"query": "Salut! qu'est qu'on a prévu de bon pour ce soir?"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "time data" not in data["spoken_response"]
        assert "Impossible de récupérer le repas" not in data["spoken_response"]
        assert "Lasagnes maison" in data["spoken_response"]


def test_interact_set_meal_plan_matches_recipe_with_hyphen_without_warning():
    """Vérifie que 'vas pour un croque monsieur' (meal='croque-monsieur') trouve 'Croque monsieur' et planifie sans avertissement."""
    from app.connectors.sheets.models import Recipe, DayMealPlan
    from datetime import date, timedelta

    mock_connector = MagicMock()
    mock_connector.get_recipe_ingredients.return_value = Recipe(
        name="Croque monsieur",
        category="Sandwich",
        category_2="Chaud",
        is_complete=True,
        ingredients=["Pain de mie", "Jambon", "Fromage croque"],
    )
    mock_connector.set_meal_plan.return_value = DayMealPlan(
        date_str=(date.today() + timedelta(days=1)).strftime("%d/%m/%Y"),
        day_name="Samedi",
        lunch="Croque monsieur",
        dinner=None,
    )
    set_meals_connector(mock_connector)

    smart_parsed = ParsedIntent(
        intent=IntentType.SET_MEAL_PLAN,
        confidence=0.98,
        parameters={"meal": "croque-monsieur", "period": "midi", "target_date": "demain"},
        raw_query="vas pour un croque monsieur",
    )

    with patch("app.main.get_nlu_service") as mock_get_nlu:
        mock_nlu = AsyncMock()
        mock_nlu.parse.return_value = smart_parsed
        mock_get_nlu.return_value = mock_nlu

        res = client.post(
            "/api/v1/interact",
            json={"query": "vas pour un croque monsieur"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        # Ne doit PAS demander de confirmation car la recette existe
        assert "n'est pas répertoriée" not in data["spoken_response"]
        assert "Attention" not in data["spoken_response"]
        assert "C'est noté, j'ai planifié" in data["spoken_response"]
        mock_connector.set_meal_plan.assert_called_once()



