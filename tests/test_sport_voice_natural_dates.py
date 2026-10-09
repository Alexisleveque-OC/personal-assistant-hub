"""Tests unitaires pour l'Étape 5 : Ergonomie vocale, formulations naturelles et tolérances linguistiques."""
from datetime import date, timedelta
from unittest.mock import MagicMock
import pytest

from app.core.date_resolver import format_natural_spoken_date
from app.core.models import IntentType, ParsedIntent
from app.connectors.sheets.sport_models import (
    SportSession,
    SportSessionPlan,
    SportSessionStatus,
    SportSessionType,
)
from app.handlers.sport_handler import handle_sport_intent
from app.core.intent_parser import IntentParser


def test_format_natural_spoken_date_relative_and_calendar():
    """Vérifie le formatage oral fluide des dates relatives et calendaires."""
    ref = date(2026, 10, 8)  # Jeudi 8 octobre 2026

    # Relatifs immédiats avec préposition
    assert format_natural_spoken_date(ref, reference_date=ref, preposition=True) == "d'aujourd'hui"
    assert format_natural_spoken_date(ref + timedelta(days=1), reference_date=ref, preposition=True) == "de demain"
    assert format_natural_spoken_date(ref + timedelta(days=2), reference_date=ref, preposition=True) == "d'après-demain"
    assert format_natural_spoken_date(ref - timedelta(days=1), reference_date=ref, preposition=True) == "d'hier"
    assert format_natural_spoken_date(ref - timedelta(days=2), reference_date=ref, preposition=True) == "d'avant-hier"

    # Sans préposition
    assert format_natural_spoken_date(ref, reference_date=ref, preposition=False) == "aujourd'hui"
    assert format_natural_spoken_date(ref + timedelta(days=1), reference_date=ref, preposition=False) == "demain"
    assert format_natural_spoken_date(ref - timedelta(days=1), reference_date=ref, preposition=False) == "hier"

    # Dates calendaires même année (au-delà de 2 jours)
    past_date = date(2026, 10, 4)  # Dimanche 4 octobre 2026
    assert format_natural_spoken_date(past_date, reference_date=ref, preposition=True) == "du dimanche 4 octobre"
    assert format_natural_spoken_date(past_date, reference_date=ref, preposition=False) == "dimanche 4 octobre"

    # Date avec année différente
    diff_year = date(2025, 10, 6)
    assert format_natural_spoken_date(diff_year, reference_date=ref, preposition=True) == "du lundi 6 octobre 2025"


@pytest.mark.asyncio
async def test_sport_handler_spoken_response_natural_dates():
    """Vérifie que la consultation d'une séance adapte le temps verbal et la date sans hardcoder 'aujourd'hui'."""
    today = date.today()
    mock_connector = MagicMock()

    # 1. Séance pour DEMAIN
    tomorrow = today + timedelta(days=1)
    tomorrow_session = SportSession(
        date=tomorrow,
        semaine=tomorrow.isocalendar()[1],
        statut=SportSessionStatus.PLANIFIE,
        type_seance=SportSessionType.EF,
        distance_km=8.0,
        duree_secondes=2700,
        programme="Footing en aisance",
    )
    mock_connector.get_session.return_value = tomorrow_session

    parsed_tomorrow = ParsedIntent(
        intent=IntentType.GET_SPORT_SESSION,
        confidence=0.95,
        parameters={"target_date": "demain"},
        raw_query="c'est quoi ma séance de demain",
    )
    spoken, _ = await handle_sport_intent(parsed_tomorrow, "c'est quoi ma séance de demain", {}, mock_connector, {})
    assert "Pour demain" in spoken
    assert "vous avez une séance de" in spoken
    assert "Pour aujourd'hui" not in spoken

    # 2. Séance passée pour HIER
    yesterday = today - timedelta(days=1)
    yesterday_session = SportSession(
        date=yesterday,
        semaine=yesterday.isocalendar()[1],
        statut=SportSessionStatus.REALISE,
        type_seance=SportSessionType.FRACTIONNE,
        distance_km=10.0,
        duree_secondes=3300,
        programme="10x400m",
    )
    mock_connector.get_session.return_value = yesterday_session

    parsed_yesterday = ParsedIntent(
        intent=IntentType.GET_SPORT_SESSION,
        confidence=0.95,
        parameters={"target_date": "hier"},
        raw_query="c'était quoi ma séance d'hier",
    )
    spoken, _ = await handle_sport_intent(parsed_yesterday, "c'était quoi ma séance d'hier", {}, mock_connector, {})
    assert "Pour hier" in spoken
    assert "vous aviez une séance de" in spoken
    assert "Pour aujourd'hui" not in spoken

    # 3. Jour de repos passé
    mock_connector.get_session.return_value = None
    spoken_rest, _ = await handle_sport_intent(parsed_yesterday, "c'était quoi ma séance d'hier", {}, mock_connector, {})
    assert "Aucune séance n'était planifiée" in spoken_rest
    assert "C'était une journée de repos" in spoken_rest


@pytest.mark.asyncio
async def test_sport_handler_update_and_plan_natural_phrasing():
    """Vérifie que la mise à jour et la planification utilisent une oralisation fluide."""
    today = date.today()
    yesterday = today - timedelta(days=1)
    mock_connector = MagicMock()

    # Mise à jour pour hier
    updated_session = SportSession(
        date=yesterday,
        semaine=yesterday.isocalendar()[1],
        statut=SportSessionStatus.REALISE,
        type_seance=SportSessionType.EF,
        distance_km=7.5,
        duree_secondes=2700,
        ressenti_rpe=7,
        notes="bonne sensation",
    )
    mock_connector.update_session.return_value = updated_session

    parsed_update = ParsedIntent(
        intent=IntentType.UPDATE_SPORT_SESSION,
        confidence=0.95,
        parameters={"target_date": "hier", "ressenti_rpe": 7},
        raw_query="modifier ma séance d'hier ressenti à 7",
    )
    spoken, _ = await handle_sport_intent(parsed_update, "modifier ma séance d'hier ressenti à 7", {}, mock_connector, {})
    assert "séance d'hier" in spoken
    assert "avec un ressenti de 7/10" in spoken

    # Planification pour demain
    tomorrow = today + timedelta(days=1)
    mock_connector.plan_session.return_value = SportSession(
        date=tomorrow,
        semaine=tomorrow.isocalendar()[1],
        statut=SportSessionStatus.PLANIFIE,
        type_seance=SportSessionType.EF,
        distance_km=6.0,
        duree_secondes=2160,
    )
    parsed_plan = ParsedIntent(
        intent=IntentType.PLAN_SPORT_SESSION,
        confidence=0.95,
        parameters={"target_date": tomorrow, "type_seance": "EF"},
        raw_query="planifier mon footing pour demain",
    )
    spoken_plan, _ = await handle_sport_intent(parsed_plan, "planifier mon footing pour demain", {}, mock_connector, {})
    assert "pour demain" in spoken_plan


def test_intent_parser_infinitives_and_lexical_variants():
    """Vérifie le support de l'infinitif et des variantes de vocabulaire dans l'analyse NLU."""
    parser = IntentParser()

    # 1. Infinitif pour modification
    p1 = parser.parse("modifier ma séance d'hier avec un ressenti à 8")
    assert p1.intent == IntentType.UPDATE_SPORT_SESSION
    assert p1.parameters.get("target_date") == "hier"
    assert p1.parameters.get("ressenti_rpe") == 8

    p2 = parser.parse("changer le rpe de ma séance de dimanche à 7")
    assert p2.intent == IntentType.UPDATE_SPORT_SESSION
    assert p2.parameters.get("target_date") == "dimanche"
    assert p2.parameters.get("ressenti_rpe") == 7

    p3 = parser.parse("mettre à jour ma séance d'hier : douleur au tibia")
    assert p3.intent == IntentType.UPDATE_SPORT_SESSION
    assert p3.parameters.get("target_date") == "hier"
    assert "douleur au tibia" in p3.parameters.get("notes", "")

    # 2. Infinitif pour planification
    p4 = parser.parse("planifier un footing jeudi")
    assert p4.intent == IntentType.PLAN_SPORT_SESSION
    assert p4.parameters.get("day_name") == "jeudi"

    p5 = parser.parse("prévoir une séance de renfo pour vendredi")
    assert p5.intent == IntentType.PLAN_SPORT_SESSION
    assert p5.parameters.get("type_seance") == "Renforcement"

    # 3. Variantes lexicales Renforcement ("renfort", "muscu", "ppg", "gainage")
    p6 = parser.parse("j'ai fait 30 minutes de renfort ressenti 6")
    assert p6.intent == IntentType.LOG_SPORT_SESSION
    assert p6.parameters.get("type_seance") == "Renforcement"
    assert p6.parameters.get("duration_seconds") == 1800
    assert p6.parameters.get("ressenti_rpe") == 6

    p7 = parser.parse("enregistre 45 min de muscu")
    assert p7.intent == IntentType.LOG_SPORT_SESSION
    assert p7.parameters.get("type_seance") == "Renforcement"
    assert p7.parameters.get("duration_seconds") == 2700

    p8 = parser.parse("ma dernière séance de muscu")
    assert p8.intent == IntentType.GET_SPORT_SESSION
    assert p8.parameters.get("last_session") is True
    assert p8.parameters.get("session_type") == "Renforcement"
