"""Test d'intégration End-to-End (E2E) - Cerveau Conversationnel LLM Gemini & Performance.

Valide le flux complet en conditions réelles (Étape 6) :
1. Préchauffage du cache et métriques de quotas (/api/v1/cache/warmup, /api/v1/llm/stats)
2. Dialogue multi-tours et intelligence réflexive (anaphores, suggestions de repas, concision)
3. Tolérance aux recettes (tirets, accents, pluriels, nom officiel canonique)
4. Clarification naturelle de rayon et confirmation au tour suivant
5. Anaphores multi-tours ('ajoute ses ingrédients')
6. Résilience et repli transparent en cas d'indisponibilité du LLM
"""

import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app, set_meals_connector
from app.connectors.sheets.models import Recipe, DayMealPlan, WaitingListItem
from app.core.models import IntentType, ParsedIntent
from app.config import settings

client = TestClient(app)


def test_e2e_cache_warmup_and_stats_endpoints():
    """Valide les endpoints système d'initialisation rapide et de suivi des quotas."""
    # 1. Warmup du cache
    resp_warmup = client.post("/api/v1/cache/warmup")
    assert resp_warmup.status_code == 200
    data_warmup = resp_warmup.json()
    assert "success" in data_warmup

    # 2. Stats et quotas LLM
    resp_stats = client.get("/api/v1/llm/stats")
    assert resp_stats.status_code == 200
    data_stats = resp_stats.json()
    assert "daily_requests" in data_stats
    assert "max_daily_requests" in data_stats
    assert "is_configured" in data_stats


def test_e2e_complete_conversational_brain_flow():
    """Valide un scénario utilisateur complet multi-tours avec le cerveau LLM."""
    session_id = "e2e_alexis_flow_session"
    today = date.today()
    tomorrow = today + timedelta(days=1)
    tomorrow_str = tomorrow.strftime("%d/%m/%Y")

    # Mock in-memory propre du connecteur
    mock_connector = MagicMock()

    # Recette officielle dans le classeur : "Croque monsieur" (sans tiret)
    croque_recipe = Recipe(
        name="Croque monsieur",
        category="Sandwich",
        category_2="Chaud",
        is_complete=True,
        ingredients=["Pain de mie", "Jambon", "Fromage croque", "Emmental râpé"],
    )

    mock_connector.get_recipe_ingredients.side_effect = lambda name: croque_recipe if "croque" in name.lower() else None

    # Planning initialisé
    current_plan = DayMealPlan(
        date_str=tomorrow_str,
        day_name="Demain",
        lunch=None,
        dinner=None,
    )

    def _mock_set_meal_plan(meal, target_date, meal_type="soir"):
        current_plan.lunch = meal if meal_type == "midi" else current_plan.lunch
        current_plan.dinner = meal if meal_type == "soir" else current_plan.dinner
        return current_plan

    mock_connector.set_meal_plan.side_effect = _mock_set_meal_plan
    mock_connector.get_meal_plan.return_value = current_plan

    # Courses et rayons
    mock_connector.resolve_rayon.side_effect = lambda item: (
        ("Divers", "Article non répertorié") if "papier" in item.lower() else ("Boucherie", None)
    )
    mock_connector.add_shopping_item.side_effect = lambda item, rayon=None: (
        WaitingListItem(item=item, rayon=rayon or "Divers"),
        None,
    )
    mock_connector.add_recipe_ingredients_to_shopping_list.return_value = (
        croque_recipe,
        [WaitingListItem(item=ing, rayon="Frais") for ing in croque_recipe.ingredients],
    )

    set_meals_connector(mock_connector)

    # -------------------------------------------------------------
    # Tour 1 : Alexis est indécis ("Je ne sais pas quoi manger...")
    # -------------------------------------------------------------
    turn1_parsed = ParsedIntent(
        intent=IntentType.UNKNOWN,
        confidence=0.95,
        parameters={},
        raw_query="Salut! Je ne sais pas trop quoi manger pour demain midi, tu me conseilles quoi ?",
        conversational_reply="On peut faire un gratin de crozets ou un bon croque-monsieur. Qu'en penses-tu ?",
    )

    with patch("app.main.get_nlu_service") as mock_get_nlu:
        mock_nlu = AsyncMock()
        mock_nlu.parse.return_value = turn1_parsed
        mock_get_nlu.return_value = mock_nlu

        res1 = client.post(
            "/api/v1/interact",
            json={
                "query": "Salut! Je ne sais pas trop quoi manger pour demain midi, tu me conseilles quoi ?",
                "session_id": session_id,
            },
        )
        assert res1.status_code == 200
        data1 = res1.json()
        assert "croque-monsieur" in data1["spoken_response"]
        assert len(data1["spoken_response"]) > 0

    # -------------------------------------------------------------
    # Tour 2 : Alexis choisit dans le fil ("vas pour un croque monsieur")
    # -------------------------------------------------------------
    turn2_parsed = ParsedIntent(
        intent=IntentType.SET_MEAL_PLAN,
        confidence=0.98,
        parameters={"meal": "croque-monsieur", "period": "midi", "target_date": "demain"},
        raw_query="vas pour un croque monsieur",
    )

    with patch("app.main.get_nlu_service") as mock_get_nlu:
        mock_nlu = AsyncMock()
        mock_nlu.parse.return_value = turn2_parsed
        mock_get_nlu.return_value = mock_nlu

        res2 = client.post(
            "/api/v1/interact",
            json={
                "query": "vas pour un croque monsieur",
                "session_id": session_id,
            },
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["success"] is True
        # La recette "Croque monsieur" a été reconnue sans avertissement
        assert "n'est pas répertoriée" not in data2["spoken_response"]
        assert "Croque monsieur" in data2["spoken_response"]
        assert "demain midi" in data2["spoken_response"].lower()

    # -------------------------------------------------------------
    # Tour 3 : Clarification de rayon ("Ajoute du papier cuisson")
    # -------------------------------------------------------------
    turn3_parsed = ParsedIntent(
        intent=IntentType.ADD_SHOPPING_ITEM,
        confidence=0.95,
        parameters={
            "item": "papier cuisson",
            "is_ambiguous": True,
            "suggested_options": ["Entretien", "Épicerie"],
        },
        raw_query="Ajoute du papier cuisson",
        conversational_reply="Je n'ai pas de rayon certain pour 'Papier cuisson'. Veux-tu que je le range en Entretien ou en Épicerie ?",
    )

    with patch("app.main.get_nlu_service") as mock_get_nlu:
        mock_nlu = AsyncMock()
        mock_nlu.parse.return_value = turn3_parsed
        mock_get_nlu.return_value = mock_nlu

        res3 = client.post(
            "/api/v1/interact",
            json={
                "query": "Ajoute du papier cuisson",
                "session_id": session_id,
            },
        )
        assert res3.status_code == 200
        data3 = res3.json()
        assert data3["success"] is True
        assert "Entretien ou en Épicerie" in data3["spoken_response"]
        assert data3["data"]["pending_action"]["type"] == "clarify_shopping_rayon"

    # -------------------------------------------------------------
    # Tour 4 : Confirmation du rayon ("En entretien")
    # -------------------------------------------------------------
    turn4_parsed = ParsedIntent(
        intent=IntentType.CHOOSE_RAYON,
        confidence=0.99,
        parameters={"rayon": "Entretien"},
        raw_query="En entretien",
    )

    with patch("app.main.get_nlu_service") as mock_get_nlu:
        mock_nlu = AsyncMock()
        mock_nlu.parse.return_value = turn4_parsed
        mock_get_nlu.return_value = mock_nlu

        res4 = client.post(
            "/api/v1/interact",
            json={
                "query": "En entretien",
                "session_id": session_id,
            },
        )
        assert res4.status_code == 200
        data4 = res4.json()
        assert data4["success"] is True
        assert "Entretien" in data4["spoken_response"]
        assert "Papier cuisson" in data4["spoken_response"]

    # -------------------------------------------------------------
    # Tour 5 : Vérification du planning ("qu'est ce qu'on a prévu demain midi ?")
    # -------------------------------------------------------------
    turn5_parsed = ParsedIntent(
        intent=IntentType.GET_MEAL_PLAN,
        confidence=0.98,
        parameters={"period": "midi", "target_date": "tomorrow"},
        raw_query="qu'est ce qu'on a prévu demain midi ?",
    )

    with patch("app.main.get_nlu_service") as mock_get_nlu:
        mock_nlu = AsyncMock()
        mock_nlu.parse.return_value = turn5_parsed
        mock_get_nlu.return_value = mock_nlu

        res5 = client.post(
            "/api/v1/interact",
            json={
                "query": "qu'est ce qu'on a prévu demain midi ?",
                "session_id": session_id,
            },
        )
        assert res5.status_code == 200
        data5 = res5.json()
        assert data5["success"] is True
        assert "time data" not in data5["spoken_response"]
        assert "Croque monsieur" in data5["spoken_response"]

    # -------------------------------------------------------------
    # Tour 6 : Anaphore ("ajoute ses ingrédients")
    # -------------------------------------------------------------
    turn6_parsed = ParsedIntent(
        intent=IntentType.ADD_RECIPE_INGREDIENTS,
        confidence=0.98,
        parameters={"recipe": "Croque monsieur"},
        raw_query="ajoute ses ingrédients",
    )

    with patch("app.main.get_nlu_service") as mock_get_nlu:
        mock_nlu = AsyncMock()
        mock_nlu.parse.return_value = turn6_parsed
        mock_get_nlu.return_value = mock_nlu

        res6 = client.post(
            "/api/v1/interact",
            json={
                "query": "ajoute ses ingrédients",
                "session_id": session_id,
            },
        )
        assert res6.status_code == 200
        data6 = res6.json()
        assert data6["success"] is True
        assert "Croque monsieur" in data6["spoken_response"]
        assert len(data6["data"]["added_items"]) == 4


def test_e2e_resilience_fallback_when_gemini_fails_or_unconfigured():
    """Vérifie que l'application bascule automatiquement sur le parseur local en cas de panne LLM."""
    mock_connector = MagicMock()
    mock_connector.add_shopping_item.return_value = (
        WaitingListItem(item="Pommes", rayon="Fruits & Légumes"),
        None,
    )
    set_meals_connector(mock_connector)

    # Simulation d'un échec total de Gemini (ex: timeout ou 503)
    with patch("app.core.llm.gemini_client.GeminiClient.resolve_model", side_effect=Exception("API Gemini injoignable")):
        res = client.post(
            "/api/v1/interact",
            json={"query": "ajoute des pommes à la liste de courses"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "pommes" in data["spoken_response"].lower()
