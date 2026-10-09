"""Tests unitaires TDD pour la résolution sémantique temporelle (« Ma dernière séance »)."""
from datetime import date
import os
import tempfile
import pytest

from app.core.database import DatabaseManager, set_database_manager
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.connectors.sheets.sport_models import (
    SportSessionCreate,
    SportSessionPlan,
    SportSessionStatus,
    SportSessionType,
)
from app.core.intent_parser import IntentParser
from app.core.models import IntentType
from app.handlers.sport_handler import handle_sport_intent


@pytest.fixture
def temp_sql_connector():
    """Crée une instance isolée de DatabaseManager et SqlSportConnector."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    db.init_db()
    set_database_manager(db)
    connector = SqlSportConnector(db_manager=db)
    yield connector
    set_database_manager(None)
    if os.path.exists(path):
        os.remove(path)


def test_intent_parser_detects_last_session_variants():
    """Vérifie la détection de l'intention GET_SPORT_SESSION avec paramètre last pour diverses formulations."""
    parser = IntentParser()

    # 1. Formulation générale
    res1 = parser.parse("C'est quoi ma dernière séance ?")
    assert res1.intent == IntentType.GET_SPORT_SESSION
    assert res1.parameters.get("target_date") == "last" or res1.parameters.get("last_session") is True

    res2 = parser.parse("Rappelle-moi ma dernière séance")
    assert res2.intent == IntentType.GET_SPORT_SESSION
    assert res2.parameters.get("last_session") is True

    # 2. Formulation ciblant un footing / course
    res3 = parser.parse("C'est quoi mon dernier footing ?")
    assert res3.intent == IntentType.GET_SPORT_SESSION
    assert res3.parameters.get("last_session") is True
    assert res3.parameters.get("session_type") == "EF"

    res3_course = parser.parse("Rappelle-moi mon dernier footing")
    assert res3_course.intent == IntentType.GET_SPORT_SESSION
    assert res3_course.parameters.get("last_session") is True

    # 3. Formulation ciblant un renforcement
    res4 = parser.parse("Ma dernière séance de renfo")
    assert res4.intent == IntentType.GET_SPORT_SESSION
    assert res4.parameters.get("last_session") is True
    assert res4.parameters.get("session_type") == "Renforcement"

    res5 = parser.parse("Mon dernier renforcement")
    assert res5.intent == IntentType.GET_SPORT_SESSION
    assert res5.parameters.get("last_session") is True
    assert res5.parameters.get("session_type") == "Renforcement"


def test_sql_sport_connector_get_last_session(temp_sql_connector):
    """Vérifie que get_last_session résout la dernière séance réelle en base SQLite."""
    # Insertion de séances avec dates échelonnées
    temp_sql_connector.log_session(
        SportSessionCreate(
            date=date(2026, 10, 1),
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.EF,
            distance_km=8.0,
            duree_secondes=2880,
            ressenti_rpe=5,
        )
    )
    temp_sql_connector.log_session(
        SportSessionCreate(
            date=date(2026, 10, 3),
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.RENFORCEMENT,
            duree_secondes=1800,
            ressenti_rpe=6,
        )
    )
    temp_sql_connector.log_session(
        SportSessionCreate(
            date=date(2026, 10, 5),
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.FRACTIONNE,
            distance_km=10.0,
            duree_secondes=3300,
            ressenti_rpe=8,
            programme="6x400m",
        )
    )
    # Séance future prévue : ne doit pas être prise comme dernière séance réalisée !
    temp_sql_connector.plan_session(
        SportSessionPlan(
            date=date(2026, 10, 12),
            type_seance=SportSessionType.SORTIE_LONGUE,
            distance_km_cible=15.0,
        )
    )

    # 1. Dernière séance globale réalisée -> Fractionné du 5 octobre
    last_overall = temp_sql_connector.get_last_session()
    assert last_overall is not None
    assert last_overall.date == date(2026, 10, 5)
    assert last_overall.type_seance == SportSessionType.FRACTIONNE

    # 2. Dernier renforcement réalisé -> Renfo du 3 octobre
    last_renfo = temp_sql_connector.get_last_session(session_type=SportSessionType.RENFORCEMENT)
    assert last_renfo is not None
    assert last_renfo.date == date(2026, 10, 3)
    assert last_renfo.type_seance == SportSessionType.RENFORCEMENT

    # 3. Dernier footing réalisé -> EF du 1er octobre
    last_ef = temp_sql_connector.get_last_session(session_type=SportSessionType.EF)
    assert last_ef is not None
    assert last_ef.date == date(2026, 10, 1)
    assert last_ef.type_seance == SportSessionType.EF


@pytest.mark.asyncio
async def test_sport_handler_resolves_last_session_dynamically(temp_sql_connector):
    """Vérifie que handle_sport_intent interroge la base au lieu de supposer date.today()."""
    # Enregistrement d'une séance au 5 octobre (alors qu'aujourd'hui est le 8 octobre)
    temp_sql_connector.log_session(
        SportSessionCreate(
            date=date(2026, 10, 5),
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.FRACTIONNE,
            distance_km=10.0,
            duree_secondes=3300,
            programme="6x400m à 3'45/km",
        )
    )

    parser = IntentParser()
    parsed = parser.parse("C'est quoi ma dernière séance ?")

    spoken, data = await handle_sport_intent(
        parsed=parsed,
        raw_query="C'est quoi ma dernière séance ?",
        session_ctx={},
        sport_connector=temp_sql_connector,
        data={},
    )

    assert "session" in data
    assert data["session"]["date"] == "2026-10-05"
    assert "dernière séance" in spoken.lower()
    assert "Fractionné" in spoken
    assert "10 km" in spoken


@pytest.mark.asyncio
async def test_sport_handler_last_session_empty_history(temp_sql_connector):
    """Vérifie la réponse courtoise lorsqu'aucune séance passée n'est présente en base."""
    parser = IntentParser()
    parsed = parser.parse("C'est quoi ma dernière séance ?")

    spoken, data = await handle_sport_intent(
        parsed=parsed,
        raw_query="C'est quoi ma dernière séance ?",
        session_ctx={},
        sport_connector=temp_sql_connector,
        data={},
    )

    assert "session" not in data
    assert "Aucune séance précédente" in spoken
