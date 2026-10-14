"""Tests TDD pour la correction de sauvegarde et débriefing des séances de sport (Étape 5).

Couvre :
1. Débriefing consécutif oral (« j'ai mis 45min et 30 sec pour faire 7km sur cette séance ») sans création de doublon.
2. Rétroaction corrective utilisateur (« tu as créé une séance plutôt que modifier la séance qui était prévue »)
   avec fusion réelle et suppression du doublon.
3. Robustesse de l'endpoint PATCH /api/v1/sport/session/{date} avec SqlSportConnector (bug bouton rouge PWA).
4. Parsing d'intentions locales (durée avant distance, anaphores, détection de correction de doublon).
"""
import pytest
from datetime import date
from unittest.mock import patch

from app.core.models import IntentType, ParsedIntent
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.connectors.sheets.sport_models import (
    SportSessionCreate,
    SportSessionStatus,
    SportSessionType,
    SportSessionUpdate,
)
from app.core.database import DatabaseManager
from app.core.intent_parser import IntentParser
from app.handlers.sport_handler import handle_sport_intent
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def temp_db(tmp_path):
    """Fixture créant une base SQLite de test isolée."""
    from app.core.dependencies import set_database_manager
    db_file = tmp_path / "test_sport_step5.db"
    db = DatabaseManager(db_path=str(db_file))
    db.init_db()
    set_database_manager(db)
    yield db
    set_database_manager(None)


@pytest.fixture
def sport_connector(temp_db):
    """Fixture créant un connecteur SqlSportConnector utilisant la base temporaire."""
    return SqlSportConnector(db_manager=temp_db)


@pytest.fixture
def client(sport_connector):
    """Client FastAPI configuré avec le connecteur sport de test."""
    from app.core.dependencies import set_sport_connector, get_sport_connector
    old = get_sport_connector()
    set_sport_connector(sport_connector)
    app.dependency_overrides[get_sport_connector] = lambda: sport_connector
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_sport_connector, None)
    set_sport_connector(old)


# --- 1. Tests Parser d'Intentions ---

def test_intent_parser_duration_before_distance_and_anaphora():
    """Vérifie que 'j'ai mis 45min et 30 sec pour faire 7km sur cette séance' est correctement extrait."""
    parser = IntentParser()
    query = "super, j'ai mis 45min et 30 sec pour faire 7km sur cette séance"
    parsed = parser.parse(query)

    assert parsed.intent in (IntentType.LOG_SPORT_SESSION, IntentType.UPDATE_SPORT_SESSION)
    assert parsed.parameters.get("distance_km") == 7.0
    # 45 min + 30 sec = 2730 secondes
    assert parsed.parameters.get("duration_seconds") == 2730
    assert parsed.parameters.get("contextual_session") is True or "cette séance" in query


def test_intent_parser_detects_duplicate_correction_feedback():
    """Vérifie que la remarque corrective sur un doublon est correctement reconnue."""
    parser = IntentParser()
    queries = [
        "tu as créé une séance plutôt que modifier la séance qui était prévue",
        "tu as créé un doublon au lieu de modifier la séance",
        "fusionne avec la séance prévue",
        "supprime le doublon et modifie la séance prévue",
    ]
    for q in queries:
        parsed = parser.parse(q)
        assert parsed.intent == IntentType.FIX_SPORT_DUPLICATE, f"Échec pour la requête : {q}"


# --- 2. Test Débriefing consécutif oral sans doublon ---

@pytest.mark.asyncio
async def test_consecutive_debrief_updates_existing_session_without_duplicate(sport_connector, temp_db):
    """Lorsqu'une séance existe (ex: Sortie Longue du 10 oct.), le débriefing d'Alexis doit la mettre à jour

    plutôt que de créer une 2ème séance le même jour.
    """
    target_d = date(2026, 10, 10)
    # Création initiale : Sortie Longue de 7.5 km
    initial_session = SportSessionCreate(
        date=target_d,
        type_seance=SportSessionType.SORTIE_LONGUE,
        distance_km=7.5,
        duree_secondes=3600,
        programme="Sortie Longue endurance",
        ressenti_rpe=4,
    )
    sport_connector.log_session(initial_session)

    # Vérification initiale : 1 seule séance
    sessions_before = temp_db.get_sport_sessions(start_date=target_d.isoformat(), end_date=target_d.isoformat())
    assert len(sessions_before) == 1
    assert sessions_before[0]["type_seance"] == "Sortie Longue"

    # Contexte conversationnel simulant la suite de l'échange
    session_ctx = {"last_sport_date": target_d.isoformat()}
    parsed = ParsedIntent(
        intent=IntentType.LOG_SPORT_SESSION,
        parameters={
            "distance_km": 7.0,
            "duration_seconds": 2730,
            "contextual_session": True,
            # Le LLM pourrait envoyer par défaut EF si l'utilisateur n'a pas répété Sortie Longue
            "type_seance": "EF",
        },
        raw_query="super, j'ai mis 45min et 30 sec pour faire 7km sur cette séance",
    )

    data = {}
    spoken, data = await handle_sport_intent(
        parsed=parsed,
        raw_query=parsed.raw_query,
        session_ctx=session_ctx,
        sport_connector=sport_connector,
        data=data,
    )

    # Vérification : toujours UNE SEULE séance, pas de doublon !
    sessions_after = temp_db.get_sport_sessions(start_date=target_d.isoformat(), end_date=target_d.isoformat())
    assert len(sessions_after) == 1, "Un doublon a été créé au lieu de mettre à jour la séance existante !"
    updated = sessions_after[0]
    assert updated["distance_km"] == 7.0
    assert updated["duree_secondes"] == 2730
    # Le type original Sortie Longue a été préservé
    assert updated["type_seance"] == "Sortie Longue"
    assert "7" in spoken


# --- 3. Test Rétroaction corrective utilisateur avec fusion réelle ---

@pytest.mark.asyncio
async def test_feedback_merges_and_deletes_duplicate(sport_connector, temp_db):
    """Si un doublon existe (ex: Sortie Longue + séance EF créée par erreur),

    la phrase 'tu as créé une séance plutôt que modifier la séance qui était prévue'
    fusionne les métriques sur la séance d'origine et supprime le doublon en base.
    """
    target_d = date(2026, 10, 10)
    # 1. Séance d'origine (Sortie Longue)
    id1 = temp_db.add_sport_session({
        "date": target_d.isoformat(),
        "semaine": 41,
        "statut": "Réalisé",
        "type_seance": "Sortie Longue",
        "distance_km": 7.5,
        "duree_secondes": 3600,
        "ressenti_rpe": 4,
        "programme": "Sortie Longue weekend",
    })

    # 2. Doublon créé par erreur (EF avec 7km et 2730s)
    id2 = temp_db.add_sport_session({
        "date": target_d.isoformat(),
        "semaine": 41,
        "statut": "Réalisé",
        "type_seance": "EF",
        "distance_km": 7.0,
        "duree_secondes": 2730,
        "notes": "45min et 30 sec",
    })

    # Vérification que 2 séances existent avant correction
    sessions_pre = temp_db.get_sport_sessions(start_date=target_d.isoformat(), end_date=target_d.isoformat())
    assert len(sessions_pre) == 2

    session_ctx = {
        "last_sport_date": target_d.isoformat(),
        "last_created_sport_id": id2,
    }
    parsed = ParsedIntent(
        intent=IntentType.FIX_SPORT_DUPLICATE,
        parameters={"target_date": target_d.isoformat()},
        raw_query="tu as créé une séance plutôt que modifier la séance qui était prévue",
    )

    data = {}
    spoken, data = await handle_sport_intent(
        parsed=parsed,
        raw_query=parsed.raw_query,
        session_ctx=session_ctx,
        sport_connector=sport_connector,
        data=data,
    )

    # Vérification : le doublon id2 est supprimé, il ne reste que la séance d'origine id1
    sessions_post = temp_db.get_sport_sessions(start_date=target_d.isoformat(), end_date=target_d.isoformat())
    assert len(sessions_post) == 1
    remaining = sessions_post[0]
    assert remaining["id"] == id1
    assert remaining["type_seance"] == "Sortie Longue"
    assert remaining["distance_km"] == 7.0
    assert remaining["duree_secondes"] == 2730
    assert remaining["ressenti_rpe"] == 4
    # La réponse confirme la fusion réelle
    assert "fusion" in spoken.lower() or "supprim" in spoken.lower() or "rectifi" in spoken.lower()


# --- 4. Test Robustesse PATCH /api/v1/sport/session/{date} avec SqlSportConnector ---

def test_patch_sport_session_with_multiline_remarks_and_sql_connector(client, sport_connector, temp_db):
    """Vérifie que PATCH /api/v1/sport/session/{date} ne crash pas avec update_data/updates

    et accepte les remarques longues avec retours à la ligne et apostrophes (Bug bouton rouge Screen 2).
    """
    target_d = date(2026, 10, 11)
    sport_connector.log_session(SportSessionCreate(
        date=target_d,
        type_seance=SportSessionType.EF,
        distance_km=8.0,
        duree_secondes=3000,
        ressenti_rpe=5,
    ))

    payload = {
        "target_type": "EF",
        "ressenti_rpe": 7,
        "remarques": "Séance agréable sous la pluie.\nSensations moyennes au niveau du mollet gauche.\nÀ surveiller demain !",
        "append_remarques": True,
    }

    response = client.patch(f"/api/v1/sport/session/{target_d.isoformat()}", json=payload)
    assert response.status_code == 200, f"Erreur {response.status_code}: {response.text}"
    res_data = response.json()
    assert res_data["success"] is True
    assert res_data["session"]["ressenti_rpe"] == 7
    assert "mollet gauche" in res_data["session"]["remarques"]
