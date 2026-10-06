"""Tests unitaires (TDD) pour la détection et l'extraction des intentions sportives (Otis)."""
import pytest
from app.core.models import IntentType, ParsedIntent
from app.core.intent_parser import IntentParser
from app.core.llm.nlu_service import GeminiNLUService, LLMNLUResponse


def test_intent_type_contains_sport_intents():
    """Vérifie la présence des intentions sportives dans IntentType."""
    assert IntentType.GET_SPORT_SESSION == "get_sport_session"
    assert IntentType.LOG_SPORT_SESSION == "log_sport_session"
    assert IntentType.GET_SPORT_WEEKLY_SUMMARY == "get_sport_weekly_summary"
    assert IntentType.PLAN_SPORT_SESSION == "plan_sport_session"
    assert IntentType.UPDATE_SPORT_SESSION == "update_sport_session"


def test_local_parser_detects_get_sport_session_today():
    """Le parseur local déterministe détecte la consultation de la séance du jour."""
    parser = IntentParser()
    parsed = parser.parse("Qu'est-ce que j'ai comme séance aujourd'hui ?")

    assert parsed.intent == IntentType.GET_SPORT_SESSION
    assert parsed.parameters.get("target_date") in ("today", "aujourd'hui")


def test_local_parser_detects_get_sport_session_tomorrow():
    """Détecte la consultation pour demain."""
    parser = IntentParser()
    parsed = parser.parse("C'est quoi ma course de demain ?")

    assert parsed.intent == IntentType.GET_SPORT_SESSION
    assert parsed.parameters.get("target_date") == "demain"


def test_local_parser_detects_log_sport_session():
    """Extrait les paramètres d'une séance terminée (distance, durée)."""
    parser = IntentParser()
    parsed = parser.parse("J'ai couru 8 km en 42 minutes")

    assert parsed.intent == IntentType.LOG_SPORT_SESSION
    assert parsed.parameters.get("distance_km") == 8.0
    assert parsed.parameters.get("duration_seconds") == 42 * 60


def test_local_parser_detects_log_sport_session_with_d_plus_and_rpe():
    """Extrait la distance, la durée, le dénivelé et le ressenti."""
    parser = IntentParser()
    parsed = parser.parse("J'ai couru 7.5 km en 40 minutes avec 80m de dénivelé, ressenti 6 sur 10")

    assert parsed.intent == IntentType.LOG_SPORT_SESSION
    assert parsed.parameters.get("distance_km") == 7.5
    assert parsed.parameters.get("duration_seconds") == 40 * 60
    assert parsed.parameters.get("denivele_d_plus") == 80
    assert parsed.parameters.get("ressenti_rpe") == 6


def test_local_parser_detects_get_sport_weekly_summary():
    """Détecte la demande de bilan hebdomadaire ou kilomètres cumulés."""
    parser = IntentParser()
    parsed1 = parser.parse("J'en suis à combien de kilomètres cette semaine ?")
    parsed2 = parser.parse("Quel est mon bilan de course cette semaine ?")

    assert parsed1.intent == IntentType.GET_SPORT_WEEKLY_SUMMARY
    assert parsed2.intent == IntentType.GET_SPORT_WEEKLY_SUMMARY


def test_local_parser_detects_plan_sport_session():
    """Détecte la planification d'une séance future."""
    parser = IntentParser()
    parsed = parser.parse("Planifie-moi un fractionné jeudi")

    assert parsed.intent == IntentType.PLAN_SPORT_SESSION
    assert parsed.parameters.get("type_seance") == "Fractionné"
    assert parsed.parameters.get("day_name") == "jeudi"


def test_gemini_nlu_response_validates_sport_intent():
    """Vérifie que LLMNLUResponse accepte les intentions et paramètres sportifs."""
    response = LLMNLUResponse(
        intent=IntentType.LOG_SPORT_SESSION,
        confidence=0.98,
        parameters={
            "distance_km": 10.2,
            "duration_seconds": 3200,
            "denivele_d_plus": 150,
            "ressenti_rpe": 7,
            "type_seance": "Sortie Longue",
            "notes": "Parcours vallonné",
        },
        conversational_reply="Superbe sortie de 10.2 km, Alexis ! Otis a tout consigné dans le journal.",
    )

    assert response.intent == IntentType.LOG_SPORT_SESSION
    assert response.parameters["distance_km"] == 10.2
    assert response.parameters["denivele_d_plus"] == 150
    assert "Otis" in response.conversational_reply


def test_local_parser_detects_log_renforcement_session():
    """Détecte l'enregistrement d'une séance de renforcement musculaire sans kilomètres."""
    parser = IntentParser()
    parsed = parser.parse("J'ai fait 30 minutes de renfo, ressenti 7 sur 10")

    assert parsed.intent == IntentType.LOG_SPORT_SESSION
    assert parsed.parameters.get("type_seance") == "Renforcement"
    assert parsed.parameters.get("duration_seconds") == 30 * 60
    assert parsed.parameters.get("ressenti_rpe") == 7


def test_local_parser_detects_update_sport_session_rpe_and_note():
    """Détecte la modification du ressenti RPE et de la note pour cause de périostite."""
    parser = IntentParser()
    parsed = parser.parse("Otis, modifie le ressenti de ma course de dimanche à 9 sur 10 à cause de ma périostite")

    assert parsed.intent == IntentType.UPDATE_SPORT_SESSION
    assert parsed.parameters.get("target_date") == "dimanche"
    assert parsed.parameters.get("ressenti_rpe") == 9
    assert "périostite" in parsed.parameters.get("notes", "").lower()


def test_local_parser_detects_update_sport_session_note_only():
    """Détecte l'ajout d'une note de douleur post-séance."""
    parser = IntentParser()
    parsed = parser.parse("Otis, ajoute une note sur ma course de dimanche : douleur au tibia à J+2")

    assert parsed.intent == IntentType.UPDATE_SPORT_SESSION
    assert parsed.parameters.get("target_date") == "dimanche"
    assert "douleur au tibia" in parsed.parameters.get("notes", "").lower()


def test_gemini_nlu_response_validates_update_sport_session():
    """Vérifie que LLMNLUResponse valide l'intention UPDATE_SPORT_SESSION."""
    response = LLMNLUResponse(
        intent=IntentType.UPDATE_SPORT_SESSION,
        confidence=0.95,
        parameters={
            "target_date": "dimanche",
            "ressenti_rpe": 9,
            "notes": "douleur vive périostite tibia droit",
        },
        conversational_reply="C'est bien noté Alexis, j'ai passé le ressenti de dimanche à 9. Repos et glace recommandés pour ta périostite.",
    )
    assert response.intent == IntentType.UPDATE_SPORT_SESSION
    assert response.parameters["ressenti_rpe"] == 9


def test_local_parser_detects_plan_weekly_training():
    """Détecte la demande de planification hebdomadaire globale."""
    parser = IntentParser()
    parsed = parser.parse("Otis, prévois-moi ma semaine d'entraînement")

    assert parsed.intent == IntentType.PLAN_WEEKLY_TRAINING
    assert parsed.confidence >= 0.90


def test_local_parser_detects_plan_weekly_training_deload():
    """Détecte la demande de semaine allégée ou de repos."""
    parser = IntentParser()
    parsed = parser.parse("Prévois une semaine de repos")

    assert parsed.intent == IntentType.PLAN_WEEKLY_TRAINING
    assert parsed.parameters.get("is_deload") is True


def test_gemini_nlu_response_validates_plan_weekly_training():
    """Vérifie que LLMNLUResponse valide l'intention PLAN_WEEKLY_TRAINING."""
    response = LLMNLUResponse(
        intent=IntentType.PLAN_WEEKLY_TRAINING,
        confidence=0.98,
        parameters={"user_wishes": "15 km samedi", "is_deload": False},
        conversational_reply="Je prépare ton plan personnalisé en analysant tes 4 dernières semaines.",
    )
    assert response.intent == IntentType.PLAN_WEEKLY_TRAINING
    assert response.parameters["user_wishes"] == "15 km samedi"


def test_local_parser_detects_log_planned_session_confirmation():
    """Détecte la confirmation de réalisation d'une séance prévue (ex: 'J'ai fait ma séance d'aujourd'hui', 'J'ai fait mon fractionné')."""
    parser = IntentParser()

    p1 = parser.parse("J'ai fait ma séance d'aujourd'hui")
    assert p1.intent == IntentType.LOG_SPORT_SESSION
    assert p1.parameters.get("target_date") in ("today", "aujourd'hui")

    p2 = parser.parse("J'ai fait ma séance")
    assert p2.intent == IntentType.LOG_SPORT_SESSION

    p3 = parser.parse("J'ai fait mon fractionné")
    assert p3.intent == IntentType.LOG_SPORT_SESSION
    assert p3.parameters.get("type_seance") == "Fractionné"

    p4 = parser.parse("J'ai fait ça, ressenti 7")
    assert p4.intent == IntentType.LOG_SPORT_SESSION
    assert p4.parameters.get("ressenti_rpe") == 7



