"""Tests TDD pour la correction de l'écrasement partiel et la capture de la Fréquence Cardiaque (FC).

Couvre :
1. Extraction de la fréquence max et moyenne dans le IntentParser (« ma fréquence max sur cette séance était a 156 et moyenne a 171 »).
2. Préservation sélective absolue : une mise à jour partielle (ex: FC ou RPE) ne doit JAMAIS écraser les autres champs (distance, durée, etc.) avec None ou 0.
3. Confirmation vocale explicite d'Otis pour la FC moyenne et maximale.
4. Intégrité de la Charge RPE et de la note Météo.
"""
from datetime import date
import pytest

from app.core.database import DatabaseManager
from app.core.dependencies import set_database_manager, set_sport_connector
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.connectors.sheets.sport_models import (
    SportSessionCreate,
    SportSessionPlan,
    SportSessionStatus,
    SportSessionType,
)
from app.core.intent_parser import IntentParser
from app.core.models import IntentType, ParsedIntent
from app.handlers.sport_handler import handle_sport_intent


@pytest.fixture
def temp_db(tmp_path):
    """Fixture base SQLite isolée."""
    db_file = tmp_path / "test_sport_selective_update.db"
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

def test_intent_parser_extracts_heart_rate_max_and_moy():
    """Vérifie que la phrase de débriefing de fréquence cardiaque est bien routée

    vers UPDATE_SPORT_SESSION avec fc_max=156 et fc_moyenne=171.
    """
    parser = IntentParser()
    query = "ma fréquence max sur cette séance était a 156 et moyenne a 171"
    parsed = parser.parse(query)

    assert parsed.intent == IntentType.UPDATE_SPORT_SESSION
    assert parsed.parameters.get("target_date") in ("last", "dernière", "derniere")
    assert parsed.parameters.get("fc_max") == 156
    assert parsed.parameters.get("fc_moyenne") == 171


def test_intent_parser_extracts_heart_rate_variations():
    """Vérifie les variantes courantes de saisie de fréquence cardiaque."""
    parser = IntentParser()

    # Variante A : FC moy puis FC max
    parsed_a = parser.parse("sur cette course ma fc moyenne était de 150 et max à 175")
    assert parsed_a.intent == IntentType.UPDATE_SPORT_SESSION
    assert parsed_a.parameters.get("fc_moyenne") == 150
    assert parsed_a.parameters.get("fc_max") == 175

    # Variante B : FC moyenne seule
    parsed_b = parser.parse("cardio moyen à 145 bpm sur la dernière séance")
    assert parsed_b.intent == IntentType.UPDATE_SPORT_SESSION
    assert parsed_b.parameters.get("fc_moyenne") == 145


# --- 2. Tests Préservation Sélective (Non-Écrasement à None/0) ---

@pytest.mark.asyncio
async def test_selective_update_does_not_wipe_existing_session_fields(sport_connector, temp_db):
    """Vérifie que modifier uniquement la FC ou le RPE sur une séance existante

    NE REMET PAS à zéro / None la distance, la durée, le RPE, la météo, etc.
    """
    session_date = date(2026, 10, 10)
    # Étape A : Séance enregistrée avec 5 km, 45 min 30 (2730s), RPE 5, météo 3
    initial = SportSessionCreate(
        date=session_date,
        type_seance=SportSessionType.EF,
        distance_km=5.0,
        duree_secondes=2730,
        ressenti_rpe=5,
        meteo_note=3,
        programme="Footing d'assimilation",
        remarques="Sensations légères",
    )
    sport_connector.log_session(initial)

    session_ctx = {"last_sport_date": session_date.isoformat()}

    # Étape B : Alexis ajuste uniquement sa fréquence cardiaque
    # ("ma fréquence max sur cette séance était a 156 et moyenne a 171")
    parsed_fc = ParsedIntent(
        intent=IntentType.UPDATE_SPORT_SESSION,
        confidence=0.95,
        parameters={
            "target_date": "last",
            "fc_max": 156,
            "fc_moyenne": 171,
        },
        raw_query="ma fréquence max sur cette séance était a 156 et moyenne a 171",
    )

    data = {}
    spoken, data = await handle_sport_intent(
        parsed=parsed_fc,
        raw_query="ma fréquence max sur cette séance était a 156 et moyenne a 171",
        session_ctx=session_ctx,
        sport_connector=sport_connector,
        data=data,
    )

    # Vérification dans SQLite : TOUTES les valeurs précédentes doivent être INTACTES !
    saved_session = sport_connector.get_session(session_date)
    assert saved_session is not None
    assert saved_session.distance_km == 5.0, "La distance ne doit pas avoir été remise à zéro !"
    assert saved_session.duree_secondes == 2730, "La durée ne doit pas avoir été remise à zéro !"
    assert saved_session.ressenti_rpe == 5, "Le RPE doit être conservé !"
    assert saved_session.meteo_note == 3, "La météo doit être conservée !"
    assert saved_session.fc_max == 156, "La FC max doit être mise à jour !"
    assert saved_session.fc_moyenne == 171, "La FC moyenne doit être mise à jour !"
    assert saved_session.charge_rpe == 228, "La charge RPE (45.5 * 5 = 227.5 -> arrondi pair) doit être calculée !"

    # Réponse vocale d'Otis doit mentionner la FC
    assert "156" in spoken
    assert "171" in spoken


def test_intent_parser_detects_last_sortie_longue_revision_with_rpe_a5():
    """Vérifie que 'sur ma dernière sortie longue finalement j'ai fait 7km en 45 min, avec un rpe a5...'

    est correctement classé en UPDATE_SPORT_SESSION ciblant la dernière sortie longue,
    avec extraction de distance (7.0 km), durée (2700s), rpe (5) et remarques de douleur.
    """
    parser = IntentParser()
    query = "sur ma dernière sortie longue finalement j'ai fait 7km en 45 min, avec un rpe a5, j'ai eu de bonne douleurs au molle et au tibia"
    parsed = parser.parse(query)

    assert parsed.intent == IntentType.UPDATE_SPORT_SESSION
    assert parsed.parameters.get("target_date") in ("last", "dernière", "derniere")
    assert parsed.parameters.get("target_type") == "Sortie Longue"
    assert parsed.parameters.get("distance_km") == 7.0
    assert parsed.parameters.get("duration_seconds") == 2700
    assert parsed.parameters.get("ressenti_rpe") == 5
    notes = parsed.parameters.get("notes") or parsed.parameters.get("remarques") or ""
    assert "tibia" in notes or "douleurs" in notes


def test_intent_parser_detects_informal_weather_opinion():
    """Vérifie que 'la météo était pas top, il pleuvait et il y avait de la brume, donc je mettrais 5'

    est correctement routé vers UPDATE_SPORT_SESSION avec meteo_note=5 et remarques de conditions.
    """
    parser = IntentParser()
    query = "la météo était pas top, il pleuvait et il y avait de la brume, donc je mettrais 5"
    parsed = parser.parse(query)

    assert parsed.intent == IntentType.UPDATE_SPORT_SESSION
    assert parsed.parameters.get("meteo_note") == 5
    notes = parsed.parameters.get("notes") or parsed.parameters.get("remarques") or ""
    assert "brume" in notes or "pleuvait" in notes or "météo" in notes


@pytest.mark.asyncio
async def test_update_session_targets_last_sortie_longue_specifically(sport_connector, temp_db):
    """Vérifie qu'un débriefing ciblant 'ma dernière sortie longue' met à jour la sortie longue

    (et non une autre séance plus récente comme une EF ou un renfo), sans créer de séance parasite à aujourd'hui.
    """
    # Séance 1 (10 oct) : Sortie Longue de 7.5 km
    date_sl = date(2026, 10, 10)
    sport_connector.log_session(SportSessionCreate(
        date=date_sl,
        type_seance=SportSessionType.SORTIE_LONGUE,
        distance_km=7.5,
        duree_secondes=3000,
        ressenti_rpe=4,
    ))

    # Séance 2 (11 oct) : Séance d'EF (plus récente que la sortie longue)
    date_ef = date(2026, 10, 11)
    sport_connector.log_session(SportSessionCreate(
        date=date_ef,
        type_seance=SportSessionType.EF,
        distance_km=5.0,
        duree_secondes=1800,
        ressenti_rpe=3,
    ))

    query = "sur ma dernière sortie longue finalement j'ai fait 7km en 45 min, avec un rpe a5, j'ai eu de bonne douleurs au molle et au tibia"
    parser = IntentParser()
    parsed = parser.parse(query)

    data = {}
    spoken, data = await handle_sport_intent(
        parsed=parsed,
        raw_query=query,
        session_ctx={},
        sport_connector=sport_connector,
        data=data,
    )

    # 1. Aucune séance ne doit avoir été créée à la date d'aujourd'hui (date.today())
    today_session = sport_connector.get_session(date.today())
    if date.today() not in (date_sl, date_ef):
        assert today_session is None, "Aucune séance ne doit être créée aujourd'hui lors d'une mise à jour rétroactive !"

    # 2. La sortie longue du 10 oct doit avoir été mise à jour
    sl_updated = sport_connector.get_session(date_sl)
    assert sl_updated is not None
    assert sl_updated.type_seance == SportSessionType.SORTIE_LONGUE
    assert sl_updated.distance_km == 7.0
    assert sl_updated.duree_secondes == 2700
    assert sl_updated.ressenti_rpe == 5
    assert "tibia" in (sl_updated.remarques or "").lower() or "douleurs" in (sl_updated.remarques or "").lower()


@pytest.mark.asyncio
async def test_update_last_session_targets_planned_session_when_most_recent(temp_db):
    """Vérifie qu'un débriefing de 'dernière séance d'EF' cible une séance planifiée (Prévu) si elle est plus récente qu'une séance réalisée."""
    sport_connector = SqlSportConnector(temp_db)

    # 1. Séance ancienne (24 sept) : EF Réalisée
    date_old = date(2026, 9, 24)
    sport_connector.log_session(SportSessionCreate(
        date=date_old,
        type_seance=SportSessionType.EF,
        distance_km=4.0,
        duree_secondes=1500,
        ressenti_rpe=3,
        statut=SportSessionStatus.REALISE,
    ))

    # 2. Séance plus récente (8 oct) : EF Planifiée (Prévu)
    date_planned = date(2026, 10, 8)
    sport_connector.plan_session(SportSessionPlan(
        date=date_planned,
        type_seance=SportSessionType.EF,
        distance_km_cible=4.5,
        programme="Footing de récupération",
        remarques="Écoute tes tibias",
    ))

    # Débriefing d'Alexis : "sur ma dernière séance d'EF j'ai courus 5km en 32min32, un peu de vent donc météo a 3 et RPE a 4"
    query = "sur ma dernière séance d'EF j'ai courus 5km en 32min32, un peu de vent donc météo a 3 et RPE a 4"
    parser = IntentParser()
    parsed = parser.parse(query)

    data = {}
    spoken, data = await handle_sport_intent(
        parsed=parsed,
        raw_query=query,
        session_ctx={},
        sport_connector=sport_connector,
        data=data,
    )

    # La séance ciblée doit être celle du 8 octobre
    planned_updated = sport_connector.get_session(date_planned)
    assert planned_updated is not None
    assert planned_updated.statut == SportSessionStatus.REALISE
    assert planned_updated.distance_km == 5.0
    assert planned_updated.duree_secondes == 1952  # 32m32s
    assert planned_updated.ressenti_rpe == 4
    assert planned_updated.meteo_note == 3
    assert planned_updated.charge_rpe is not None
    assert planned_updated.charge_rpe == 130

    # L'ancienne séance du 24 sept doit rester intacte (distance 4.0 km)
    old_session = sport_connector.get_session(date_old)
    assert old_session is not None
    assert old_session.distance_km == 4.0
    assert old_session.duree_secondes == 1500


