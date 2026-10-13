"""Tests TDD pour l'Étape 5.1 : Persistance Complète du Débriefing Rétroactif & Levée du Doute SQLite.

Couvre :
1. Détection de révisions d'ouverture (« Finalement sur ma dernière séance... ») vers UPDATE_SPORT_SESSION.
2. Détection de tournures informelles (« tu peux meme mettre le rpe a 5, et la météo a 3... »).
3. Persistance complète de TOUS les champs bruts (distance, durée, RPE, météo, remarques) dans SQLite via UPDATE_SPORT_SESSION.
4. Réponse vocale d'Otis explicite et détaillée levant tout doute sur la sauvegarde réelle.
"""
from datetime import date
import pytest

from app.core.database import DatabaseManager
from app.core.dependencies import set_database_manager, set_sport_connector
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.connectors.sheets.sport_models import (
    SportSessionCreate,
    SportSessionStatus,
    SportSessionType,
)
from app.core.intent_parser import IntentParser
from app.core.models import IntentType, ParsedIntent
from app.handlers.sport_handler import handle_sport_intent


@pytest.fixture
def temp_db(tmp_path):
    """Fixture base SQLite isolée."""
    db_file = tmp_path / "test_sport_step5_1.db"
    db = DatabaseManager(db_path=str(db_file))
    db.init_db()
    set_database_manager(db)
    yield db
    set_database_manager(None)


@pytest.fixture
def sport_connector(temp_db):
    """Fixture connecteur SqlSportConnector."""
    connector = SqlSportConnector(db_manager=temp_db)
    set_sport_connector(connector)
    yield connector
    set_sport_connector(None)


# --- 1. Tests Parser d'Intentions ---

def test_intent_parser_detects_retroactive_revision_opening():
    """Vérifie que 'Finalement sur ma dernière séance de sport j'ai couru 5km avec un rpe a 4 et en 45min 30'

    est routé vers UPDATE_SPORT_SESSION (et non GET_SPORT_SESSION).
    """
    parser = IntentParser()
    query = "Finalement sur ma dernière séance de sport j'ai couru 5km avec un rpe a 4 et en 45min 30"
    parsed = parser.parse(query)

    assert parsed.intent == IntentType.UPDATE_SPORT_SESSION
    assert parsed.parameters.get("target_date") in ("last", "dernière", "derniere")
    assert parsed.parameters.get("distance_km") == 5.0
    assert parsed.parameters.get("ressenti_rpe") == 4
    # 45 min + 30 sec = 2730 secondes
    assert parsed.parameters.get("duration_seconds") == 2730


def test_intent_parser_detects_informal_metric_update_with_weather():
    """Vérifie que 'tu peux meme mettre le rpe a 5, et la météo a 3...' extrait bien le RPE, la météo et les remarques."""
    parser = IntentParser()
    query = "tu peux meme mettre le rpe a 5, et la météo a 3 il y avait un peu de vent mais c'était ok. en Commentaires j'avais quand même un peu mal au jambes donc c'était un peu dur"
    parsed = parser.parse(query)

    assert parsed.intent == IntentType.UPDATE_SPORT_SESSION
    assert parsed.parameters.get("ressenti_rpe") == 5
    assert parsed.parameters.get("meteo_note") == 3
    notes = parsed.parameters.get("notes") or parsed.parameters.get("remarques") or ""
    assert "mal au jambes" in notes or "vent" in notes


# --- 2. Tests Exécution & Persistance Réelle en Base SQLite ---

@pytest.mark.asyncio
async def test_retroactive_debrief_updates_all_raw_fields_in_sqlite(sport_connector, temp_db):
    """Vérifie que la révision rétroactive et la note météo sont réellement persistées dans SQLite

    et qu'Otis récapitule les modifications dans sa réponse vocale.
    """
    session_date = date(2026, 10, 10)
    # Création initiale : séance EF de 7 km, durée 3000s, sans météo
    initial = SportSessionCreate(
        date=session_date,
        type_seance=SportSessionType.EF,
        distance_km=7.0,
        duree_secondes=3000,
        ressenti_rpe=3,
    )
    sport_connector.log_session(initial)

    session_ctx = {"last_sport_date": session_date.isoformat()}

    # 1er tour : Alexis révise sa distance (5 km au lieu de 7 km), RPE à 4 et durée (45 min 30)
    parsed_tour1 = ParsedIntent(
        intent=IntentType.UPDATE_SPORT_SESSION,
        parameters={
            "target_date": "last",
            "distance_km": 5.0,
            "duration_seconds": 2730,
            "ressenti_rpe": 4,
        },
        raw_query="Finalement sur ma dernière séance de sport j'ai couru 5km avec un rpe a 4 et en 45min 30",
    )

    data1 = {}
    spoken1, data1 = await handle_sport_intent(
        parsed=parsed_tour1,
        raw_query=parsed_tour1.raw_query,
        session_ctx=session_ctx,
        sport_connector=sport_connector,
        data=data1,
    )

    # Vérification en base SQLite après Tour 1
    session_db1 = sport_connector.get_session(session_date)
    assert session_db1 is not None
    assert session_db1.distance_km == 5.0
    assert session_db1.duree_secondes == 2730
    assert session_db1.ressenti_rpe == 4
    # La confirmation vocale doit citer la distance et la durée
    assert "5" in spoken1
    assert "45" in spoken1 or "2730" in spoken1

    # 2ème tour : Alexis ajuste le RPE à 5, la météo à 3 et ajoute des commentaires
    parsed_tour2 = ParsedIntent(
        intent=IntentType.UPDATE_SPORT_SESSION,
        parameters={
            "ressenti_rpe": 5,
            "meteo_note": 3,
            "remarques": "il y avait un peu de vent mais c'était ok. j'avais quand même un peu mal aux jambes",
            "append_remarques": True,
        },
        raw_query="tu peux meme mettre le rpe a 5, et la météo a 3 il y avait un peu de vent mais c'était ok. en Commentaires j'avais quand même un peu mal au jambes donc c'était un peu dur",
    )

    data2 = {}
    spoken2, data2 = await handle_sport_intent(
        parsed=parsed_tour2,
        raw_query=parsed_tour2.raw_query,
        session_ctx=session_ctx,
        sport_connector=sport_connector,
        data=data2,
    )

    # Vérification en base SQLite après Tour 2
    session_db2 = sport_connector.get_session(session_date)
    assert session_db2.ressenti_rpe == 5
    assert session_db2.meteo_note == 3
    assert "mal aux jambes" in session_db2.remarques or "vent" in session_db2.remarques
    # La confirmation vocale doit citer le RPE et la météo pour lever tout doute
    assert "5" in spoken2
    assert "météo" in spoken2.lower() or "3" in spoken2


@pytest.mark.asyncio
async def test_get_last_session_reflects_updated_metrics(sport_connector, temp_db):
    """Vérifie que la consultation ultérieure de la dernière séance reflète bien les 5 km mis à jour."""
    session_date = date(2026, 10, 10)
    sport_connector.log_session(SportSessionCreate(
        date=session_date,
        type_seance=SportSessionType.EF,
        distance_km=5.0,
        duree_secondes=2730,
        ressenti_rpe=5,
        meteo_note=3,
    ))

    session_ctx = {}
    parsed = ParsedIntent(
        intent=IntentType.GET_SPORT_SESSION,
        parameters={"last_session": True},
        raw_query="Comment était ma dernière séance de sport ?",
    )

    spoken, data = await handle_sport_intent(
        parsed=parsed,
        raw_query=parsed.raw_query,
        session_ctx=session_ctx,
        sport_connector=sport_connector,
        data={},
    )

    # Doit annoncer 5 km et non 7 km
    assert "5 km" in spoken or "5,0 km" in spoken or "5" in spoken
    assert "7" not in spoken
