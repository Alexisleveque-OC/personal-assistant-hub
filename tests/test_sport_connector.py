"""Tests unitaires (TDD) pour le connecteur SportConnector."""
from datetime import date, timedelta
from unittest.mock import MagicMock
import pytest

from app.connectors.sheets.sport_models import (
    SportSession,
    SportSessionCreate,
    SportSessionPlan,
    SportSessionUpdate,
    SportSessionStatus,
    SportSessionType,
    SportWeeklySummary,
)
from app.config import settings
from app.connectors.sheets.sport_connector import SportConnector


def create_mock_worksheet(title: str, records: list[list]) -> MagicMock:
    """Helper pour créer un mock de feuille gspread."""
    ws = MagicMock()
    ws.title = title
    ws.id = 123
    ws.get_all_values.return_value = records
    ws.row_values.side_effect = lambda idx: records[idx - 1] if 0 < idx <= len(records) else []
    return ws


@pytest.fixture
def mock_sport_spreadsheet():
    """Crée un classeur mocké avec des séances et une synthèse hebdomadaire."""
    today = date(2026, 10, 6)
    today_str = today.strftime("%d/%m/%Y")
    yesterday = today - timedelta(days=1)
    yesterday_str = yesterday.strftime("%d/%m/%Y")

    seances_headers = [
        "Date", "Semaine", "Statut", "Type de séance", "Distance (km)",
        "Dénivelé D+ (m)", "Km-Effort", "Temps", "Vitesse (km/h)",
        "Allure (min/km)", "ressenti dur/10", "Charge RPE",
        "FC Moy (bpm)", "FC Max (bpm)", "Météo difficile/10",
        "Programme", "Remarques", "ID Strava"
    ]

    seances_rows = [
        seances_headers,
        [
            yesterday_str, "41", "Réalisé", "EF", "6.0",
            "50", "6.5", "00:36:00", "10.0",
            "06:00", "5", "180", "142", "165", "1",
            "", "Footing tranquille", "111222333"
        ],
        [
            today_str, "41", "Prévu", "Fractionné", "5.0",
            "0", "5.0", "", "",
            "", "", "", "", "", "",
            "6x(30s/30s)", "", ""
        ],
    ]


    synthese_headers = [
        "Semaine", "Année", "Nb Séances", "Km Totaux", "D+ Total",
        "Km-Effort Total", "Durée Totale", "Allure Moyenne",
        "Évolution vs S-1 (%)", "Alerte Sécurité", "Plafond Conseillé S+1"
    ]

    synthese_rows = [
        synthese_headers,
        [
            "40", "2026", "2", "10.13", "0",
            "10.13", "00:58:18", "05:45",
            "", "🟢 Première semaine de référence", "11.1"
        ],
    ]

    ws_seances = create_mock_worksheet("Séance", seances_rows)
    ws_synthese = create_mock_worksheet("Synthese_Hebdo", synthese_rows)

    sh = MagicMock()
    sh.title = "Running"
    sh.worksheets.return_value = [ws_seances, ws_synthese]
    sh.worksheet.side_effect = lambda name: ws_seances if ("seance" in name.lower() or "séance" in name.lower()) else ws_synthese
    return sh


def test_sport_connector_initialization_mock(mock_sport_spreadsheet):
    """Vérifie l'initialisation du connecteur avec un mock en mémoire."""
    connector = SportConnector(spreadsheet=mock_sport_spreadsheet)
    assert connector.name == "sport_running"


@pytest.mark.asyncio
async def test_sport_connector_is_healthy(mock_sport_spreadsheet):
    """Vérifie le diagnostic de santé du connecteur."""
    connector = SportConnector(spreadsheet=mock_sport_spreadsheet)
    assert await connector.is_healthy() is True


def test_sport_connector_get_session_by_date(mock_sport_spreadsheet):
    """Récupère une séance planifiée ou réalisée pour une date donnée."""
    connector = SportConnector(spreadsheet=mock_sport_spreadsheet)
    target_date = date(2026, 10, 6)

    session = connector.get_session(target_date)
    assert session is not None
    assert session.date == target_date
    assert session.statut == SportSessionStatus.PLANIFIE
    assert session.type_seance == SportSessionType.FRACTIONNE
    assert session.distance_km == 5.0


def test_sport_connector_get_session_none_when_empty(mock_sport_spreadsheet):
    """Retourne None lorsqu'aucune séance n'est prévue ce jour-là."""
    connector = SportConnector(spreadsheet=mock_sport_spreadsheet)
    future_date = date(2026, 12, 25)

    session = connector.get_session(future_date)
    assert session is None


def test_sport_connector_get_week_sessions(mock_sport_spreadsheet):
    """Récupère la liste de toutes les séances d'une semaine ISO."""
    connector = SportConnector(spreadsheet=mock_sport_spreadsheet)
    sessions = connector.get_week_sessions(week_num=41, year=2026)

    assert len(sessions) == 2
    assert sessions[0].type_seance == SportSessionType.EF
    assert sessions[1].type_seance == SportSessionType.FRACTIONNE


def test_sport_connector_log_session_new(mock_sport_spreadsheet):
    """Enregistre une nouvelle séance réalisée."""
    connector = SportConnector(spreadsheet=mock_sport_spreadsheet)
    session_create = SportSessionCreate(
        date=date(2026, 10, 7),
        type_seance=SportSessionType.EF,
        distance_km=8.2,
        duree_secondes=45 * 60,
        denivele_d_plus=120,
        ressenti_rpe=6,
        meteo_note=2,
        notes="Sortie vallonnée",
    )

    logged = connector.log_session(session_create)

    assert logged.date == date(2026, 10, 7)
    assert logged.distance_km == 8.2
    assert logged.denivele_d_plus == 120
    assert logged.km_effort == 9.4  # 8.2 + 1.2
    assert logged.statut == SportSessionStatus.REALISE
    # Vérifie que la feuille Séance a reçu une mise à jour d'ajout
    ws_seances = mock_sport_spreadsheet.worksheet("Séance")
    assert ws_seances.append_row.called or ws_seances.update.called


def test_sport_connector_log_session_updates_existing_planned(mock_sport_spreadsheet):
    """Si une séance était planifiée pour aujourd'hui, log_session la transforme en Réalisé."""
    connector = SportConnector(spreadsheet=mock_sport_spreadsheet)
    today = date(2026, 10, 6)

    session_create = SportSessionCreate(
        date=today,
        type_seance=SportSessionType.FRACTIONNE,
        distance_km=5.3,
        duree_secondes=28 * 60,
        denivele_d_plus=0,
        ressenti_rpe=7,
        meteo_note=3,
        notes="Fractionné validé",
    )

    logged = connector.log_session(session_create)
    assert logged.statut == SportSessionStatus.REALISE
    assert logged.distance_km == 5.3


def test_sport_connector_plan_session(mock_sport_spreadsheet):
    """Planifie une séance future avec un objectif."""
    connector = SportConnector(spreadsheet=mock_sport_spreadsheet)
    target_date = date(2026, 10, 10)
    plan = SportSessionPlan(
        date=target_date,
        type_seance=SportSessionType.SORTIE_LONGUE,
        distance_km_cible=12.0,
        notes="Sortie dominicale en endurance",
    )

    planned = connector.plan_session(plan)
    assert planned.date == target_date
    assert planned.statut == SportSessionStatus.PLANIFIE
    assert planned.statut.value == "Prévu"
    assert planned.type_seance == SportSessionType.SORTIE_LONGUE
    assert planned.distance_km == 12.0

    # 2. Planifier à nouveau la même date met à jour la ligne sans dupliquer
    plan_updated = SportSessionPlan(
        date=target_date,
        type_seance=SportSessionType.SORTIE_LONGUE,
        distance_km_cible=14.0,
        programme="Sortie 14 km avec 3x2000m",
    )
    planned2 = connector.plan_session(plan_updated)
    assert planned2.distance_km == 14.0
    assert planned2.programme == "Sortie 14 km avec 3x2000m"


def test_sport_connector_log_session_preserves_planned_programme(mock_sport_spreadsheet):
    """Quand une séance réalisée est enregistrée, elle conserve le programme technique prévu."""
    connector = SportConnector(spreadsheet=mock_sport_spreadsheet)
    target_d = date(2026, 10, 10)

    # 1. On planifie d'abord la séance
    connector.plan_session(
        session_date=target_d,
        type_seance=SportSessionType.FRACTIONNE,
        distance_km=6.0,
        programme="2km échauffement + 6x400m à 4'20/km",
    )

    # 2. On log la séance réalisée sans repréciser le programme
    logged = connector.log_session(SportSessionCreate(
        date=target_d,
        type_seance=SportSessionType.FRACTIONNE,
        distance_km=6.2,
        duree_secondes=32 * 60,
        ressenti_rpe=7,
        notes="Bonnes sensations",
    ))

    assert logged.statut == SportSessionStatus.REALISE
    assert logged.statut.value == "Réalisé"
    assert logged.programme == "2km échauffement + 6x400m à 4'20/km"
    assert logged.distance_km == 6.2



def test_sport_connector_get_weekly_summary(mock_sport_spreadsheet):
    """Récupère le bilan hebdomadaire et calcule les alertes mini-coach."""
    connector = SportConnector(spreadsheet=mock_sport_spreadsheet)
    summary = connector.get_weekly_summary(week_num=40, year=2026)

    assert summary.semaine == 40
    assert summary.km_total == 10.13
    assert summary.nb_seances == 2
    assert summary.km_effort_total == 10.13
    assert summary.plafond_conseille_s_plus_1 > 11.0


@pytest.mark.asyncio
async def test_sport_connector_execute_action(mock_sport_spreadsheet):
    """Vérifie l'exécution des actions standardisées via execute_action."""
    connector = SportConnector(spreadsheet=mock_sport_spreadsheet)

    # 1. Action get_session
    res = await connector.execute_action("get_session", {"target_date": "2026-10-06"})
    assert res["found"] is True
    assert res["session"]["type_seance"] == "Fractionné"

    # 2. Action get_weekly_summary
    res_summary = await connector.execute_action("get_weekly_summary", {"week_num": 40, "year": 2026})
    assert res_summary["found"] is True
    assert res_summary["summary"]["km_total"] == 10.13

    # 3. Action update_session
    yesterday = date(2026, 10, 5)
    res_update = await connector.execute_action("update_session", {
        "target_date": yesterday.strftime("%d/%m/%Y"),
        "ressenti_rpe": 8,
        "notes": "Légère gêne tibia",
        "append_notes": True,
    })
    assert res_update["success"] is True
    assert res_update["session"]["ressenti_rpe"] == 8
    assert "Légère gêne tibia" in res_update["session"]["notes"]


def test_sport_connector_log_session_renforcement(mock_sport_spreadsheet):
    """Vérifie l'enregistrement d'une séance de renforcement musculaire sans distance."""
    connector = SportConnector(spreadsheet=mock_sport_spreadsheet)
    session_create = SportSessionCreate(
        date=date(2026, 10, 7),
        type_seance=SportSessionType.RENFORCEMENT,
        distance_km=None,
        duree_secondes=30 * 60,  # 30 min
        ressenti_rpe=6,
        notes="Gainage et renforcement mollets/tibias",
    )

    logged = connector.log_session(session_create)

    assert logged.type_seance == SportSessionType.RENFORCEMENT
    assert logged.distance_km is None
    assert logged.charge_rpe == 180  # 30 * 6
    assert logged.statut == SportSessionStatus.REALISE
    ws_seances = mock_sport_spreadsheet.worksheet("Séance")
    assert ws_seances.append_row.called or ws_seances.update.called


def test_sport_connector_update_session_rpe_and_notes(mock_sport_spreadsheet):
    """Vérifie la mise à jour du RPE et de la note de douleur sur une séance passée."""
    connector = SportConnector(spreadsheet=mock_sport_spreadsheet)
    yesterday = date(2026, 10, 5)

    update_payload = SportSessionUpdate(
        ressenti_rpe=9,
        notes="douleur périostite tibia J+2",
        append_notes=True,
    )

    updated = connector.update_session(yesterday, update_payload)

    assert updated.date == yesterday
    assert updated.ressenti_rpe == 9
    # Séance d'hier = 36 min -> 36 * 9 = 324 de charge RPE
    assert updated.charge_rpe == 324
    assert "douleur périostite tibia J+2" in updated.notes
    assert "Footing tranquille" in updated.notes

    ws_seances = mock_sport_spreadsheet.worksheet("Séance")
    assert ws_seances.update.called


def test_sport_connector_update_session_not_found_raises_error(mock_sport_spreadsheet):
    """Tenter de mettre à jour une séance à une date inexistante lève une exception claire."""
    connector = SportConnector(spreadsheet=mock_sport_spreadsheet)
    with pytest.raises(ValueError, match="Aucune séance"):
        connector.update_session(date(2025, 1, 1), SportSessionUpdate(ressenti_rpe=7))


def test_sport_connector_weekly_summary_includes_charge_rpe(mock_sport_spreadsheet):
    """Vérifie que la synthèse hebdomadaire inclut la charge RPE cumulée."""
    connector = SportConnector(spreadsheet=mock_sport_spreadsheet)
    # Semaine 41 : séance d'hier (36 min, RPE 5 -> 180)
    summary = connector.get_weekly_summary(week_num=41, year=2026)
    assert summary.semaine == 41
    assert summary.charge_rpe_totale >= 180


@pytest.mark.skipif(not settings.spreadsheet_sport_id, reason="SPREADSHEET_SPORT_ID non configuré")
def test_live_sport_connector_read_real_sheet():
    """Vérifie la lecture en direct sur le vrai Google Sheet d'Alexis."""
    connector = SportConnector()
    sessions = connector.get_week_sessions(week_num=40, year=2026)
    assert len(sessions) >= 2
    assert any(s.date == date(2026, 9, 28) for s in sessions)
    assert any(s.date == date(2026, 9, 30) for s in sessions)

    summary = connector.get_weekly_summary(week_num=40, year=2026)
    assert summary.semaine == 40
    assert summary.km_total >= 10.0


def test_sport_connector_with_programme_and_remarques_columns():
    """Vérifie le fonctionnement de SportConnector avec les colonnes séparées Programme et Remarques."""
    seances_headers_18 = [
        "Date", "Semaine", "Statut", "Type de séance", "Distance (km)",
        "Dénivelé D+ (m)", "Km-Effort", "Temps", "Vitesse (km/h)",
        "Allure (min/km)", "ressenti dur/10", "Charge RPE", "FC Moy (bpm)",
        "FC Max (bpm)", "Météo difficile/10", "Programme", "Remarques", "ID Strava"
    ]
    target_date = date(2026, 10, 8)
    records = [
        seances_headers_18,
        [
            target_date.strftime("%d/%m/%Y"), "41", "Réalisé", "Fractionné", "6.2",
            "50", "6.7", "00:32:00", "11.6",
            "05:10", "7", "224", "155", "178", "2",
            "5x300m à 4'30/km", "Bonne séance, mollets un peu raides", "999888777"
        ],
    ]
    ws = create_mock_worksheet("Séance", records)
    sh = MagicMock()
    sh.worksheets.return_value = [ws]
    sh.worksheet.return_value = ws

    connector = SportConnector(spreadsheet=sh)
    session = connector.get_session(target_date)

    assert session is not None
    assert session.programme == "5x300m à 4'30/km"
    assert session.remarques == "Bonne séance, mollets un peu raides"

    # Mise à jour ciblée des Remarques (ex: douleur tibia à J+1)
    updated = connector.update_session(target_date, SportSessionUpdate(
        remarques="douleur tibia post-séance",
        append_remarques=True,
    ))
    assert updated.programme == "5x300m à 4'30/km"  # Le programme reste intact !
    assert "douleur tibia post-séance" in updated.remarques
    assert "Bonne séance" in updated.remarques


def test_sport_connector_plan_weekly_sessions_batch(mock_sport_spreadsheet):
    """Vérifie l'insertion groupée en lot (batch) d'un plan hebdomadaire complet avec statut Prévu."""
    connector = SportConnector(spreadsheet=mock_sport_spreadsheet)
    plans = [
        SportSessionPlan(
            date=date(2026, 10, 12),
            type_seance=SportSessionType.FRACTIONNE,
            distance_km_cible=5.5,
            programme="15' échauffement + 8x(30s/30s) + 10' retour calme",
            remarques="Attention périostite : surface meuble",
        ),
        SportSessionPlan(
            date=date(2026, 10, 13),
            type_seance=SportSessionType.RENFORCEMENT,
            distance_km_cible=0.0,
            programme="Mollets, soléaires et gainage sans impact",
            remarques="Conseil kiné",
        ),
        SportSessionPlan(
            date=date(2026, 10, 15),
            type_seance=SportSessionType.EF,
            distance_km_cible=6.0,
            programme="Footing allure 6'30/km strictly zone 2",
            remarques="Relâchement haut du corps",
        ),
        SportSessionPlan(
            date=date(2026, 10, 17),
            type_seance=SportSessionType.SORTIE_LONGUE,
            distance_km_cible=11.0,
            programme="Sortie endurance progressive",
            remarques="Hydratation régulière",
        ),
    ]

    inserted = connector.plan_weekly_sessions(plans)

    assert len(inserted) == 4
    for s in inserted:
        assert s.statut == SportSessionStatus.PLANIFIE
        assert s.statut.value == "Prévu"

    assert inserted[0].type_seance == SportSessionType.FRACTIONNE
    assert inserted[0].distance_km == 5.5
    assert inserted[0].programme == "15' échauffement + 8x(30s/30s) + 10' retour calme"

    assert inserted[1].type_seance == SportSessionType.RENFORCEMENT
    assert inserted[1].distance_km is None or inserted[1].distance_km == 0.0

    ws = mock_sport_spreadsheet.worksheet("Séance")
    assert ws.update.called or ws.append_rows.called


def test_sport_connector_log_session_adapts_planned_session(mock_sport_spreadsheet):
    """Vérifie qu'enregistrer une séance (Strava ou dictée) sur une séance Prévue l'adapte en Réalisé en conservant son programme et type."""
    connector = SportConnector(spreadsheet=mock_sport_spreadsheet)
    # mock_sport_spreadsheet a une séance prévue le 06/10/2026 (Fractionné, 5.0 km, Programme: 6x(30s/30s))
    today = date(2026, 10, 6)

    # Simulation arrivée d'une activité Strava avec type par défaut EF
    session_create = SportSessionCreate(
        date=today,
        type_seance=SportSessionType.EF,
        distance_km=5.25,
        duree_secondes=1840,
        denivele_d_plus=30,
        ressenti_rpe=7,
        fc_moyenne=152,
        fc_max=174,
        notes="Sync Strava : Sortie midi",
    )

    logged = connector.log_session(session_create)

    # Le statut doit être passé à Réalisé
    assert logged.statut == SportSessionStatus.REALISE
    assert logged.statut.value == "Réalisé"
    # La distance et la durée sont adaptées
    assert logged.distance_km == 5.25
    assert logged.duree_secondes == 1840
    # Le programme initial doit être préservé !
    assert logged.programme == "6x(30s/30s)"
    # Le type Fractionné prévu doit être conservé plutôt que d'être écrasé par le type par défaut EF
    assert logged.type_seance == SportSessionType.FRACTIONNE
    assert logged.ressenti_rpe == 7



def test_sport_connector_synthese_caching(mock_sport_spreadsheet):
    """Vérifie que les lectures de Synthese_Hebdo sont mises en cache pour préserver le quota API."""
    connector = SportConnector(spreadsheet=mock_sport_spreadsheet)
    ws_syn = mock_sport_spreadsheet.worksheet("Synthese_Hebdo")

    # 1er appel
    connector.get_weekly_summary(week_num=41, year=2026)
    call_count_1 = ws_syn.get_all_values.call_count

    # 2ème appel immédiat (doit utiliser le cache)
    connector.get_weekly_summary(week_num=40, year=2026)
    call_count_2 = ws_syn.get_all_values.call_count

    assert call_count_2 == call_count_1


def test_sport_connector_plan_weekly_sessions_writes_target_pace_and_speed(mock_sport_spreadsheet):
    """Vérifie que plan_weekly_sessions renseigne la Vitesse cible (Col I), l'Allure cible (Col J) et le Programme (Col P)."""
    connector = SportConnector(spreadsheet=mock_sport_spreadsheet)
    plans = [
        SportSessionPlan(
            date=date(2026, 10, 15),
            type_seance=SportSessionType.EF,
            distance_km_cible=4.5,
            allure_cible="06:30/km (+/- 15s)",
            vitesse_cible="9.2 km/h (+/- 0.4 km/h)",
            programme="Endurance fondamentale en aisance",
            remarques="Sous-bois recommandé",
        )
    ]

    inserted = connector.plan_weekly_sessions(plans)
    assert len(inserted) == 1
    session = inserted[0]
    assert session.allure_cible == "06:30/km (+/- 15s)"
    assert session.vitesse_cible == "9.2 km/h (+/- 0.4 km/h)"
    assert "[Cible : 06:30/km (+/- 15s) | 9.2 km/h (+/- 0.4 km/h)]" in session.programme

    ws = mock_sport_spreadsheet.worksheet("Séance")
    assert ws.update.called or ws.append_rows.called or ws.append_row.called
    if ws.append_rows.called:
        row_payload = ws.append_rows.call_args[0][0][0]
    elif ws.update.called:
        call_args = ws.update.call_args[1].get("values") or ws.update.call_args[0][1]
        row_payload = call_args[0]
    else:
        row_payload = ws.append_row.call_args[0][0]
    # Col I (index 8) = Vitesse cible
    assert row_payload[8] == "9.2 km/h (+/- 0.4 km/h)"
    # Col J (index 9) = Allure cible
    assert row_payload[9] == "06:30/km (+/- 15s)"
    # Col P (index 15) = Programme contenant la cible
    assert "[Cible : 06:30/km (+/- 15s) | 9.2 km/h (+/- 0.4 km/h)]" in row_payload[15]


def test_sport_connector_get_weekly_summary_multicriteria(mock_sport_spreadsheet):
    """Vérifie que get_weekly_summary calcule l'évolution multicritère et la progression générale."""
    connector = SportConnector(spreadsheet=mock_sport_spreadsheet)
    summary = connector.get_weekly_summary(week_num=41, year=2026)
    assert summary.semaine == 41
    assert summary.nb_seances >= 1
    assert summary.vitesse_kmh is not None


SEANCES_HEADERS_18 = [
    "Date", "Semaine", "Statut", "Type de séance", "Distance (km)",
    "Dénivelé D+ (m)", "Km-Effort", "Temps", "Vitesse (km/h)",
    "Allure (min/km)", "ressenti dur/10", "Charge RPE", "FC Moy (bpm)",
    "FC Max (bpm)", "Météo difficile/10", "Programme", "Remarques", "ID Strava",
]


def _build_seances_only_connector(rows: list[list]) -> SportConnector:
    """Connecteur mocké avec un unique onglet 'Séance' (pas de Synthese_Hebdo)."""
    ws = create_mock_worksheet("Séance", [SEANCES_HEADERS_18, *rows])
    sh = MagicMock()
    sh.worksheets.return_value = [ws]
    sh.worksheet.return_value = ws
    return SportConnector(spreadsheet=sh)


def _realise_row(d: date, distance: str, temps: str) -> list:
    return [
        d.strftime("%d/%m/%Y"), str(d.isocalendar()[1]), "Réalisé", "EF", distance,
        "0", distance, temps, "", "", "5", "", "", "", "", "", "", "",
    ]


def test_sport_connector_week_sessions_uses_iso_year_across_new_year():
    """La semaine ISO 1 de 2026 commence le lundi 29/12/2025 : ses séances de décembre doivent être incluses."""
    monday_w1 = date.fromisocalendar(2026, 1, 1)
    assert monday_w1.year == 2025  # Pré-condition du scénario
    connector = _build_seances_only_connector([_realise_row(monday_w1 + timedelta(days=1), "5.0", "00:30:00")])

    sessions = connector.get_week_sessions(1, 2026)

    assert len(sessions) == 1
    assert sessions[0].date == monday_w1 + timedelta(days=1)


def test_sport_connector_weekly_summary_previous_week_wraps_to_previous_iso_year():
    """En semaine 1, la semaine S-1 est la dernière semaine ISO de l'année précédente (et non une 'semaine 0')."""
    monday_w1 = date.fromisocalendar(2026, 1, 1)
    last_week_prev_year = monday_w1 - timedelta(days=7)
    connector = _build_seances_only_connector([
        _realise_row(last_week_prev_year, "8.0", "00:48:00"),
        _realise_row(monday_w1 + timedelta(days=2), "6.0", "00:36:00"),
    ])

    summary = connector.get_weekly_summary(week_num=1, year=2026)

    assert summary.km_total == 6.0
    assert summary.previous_week_km_effort == 8.0
    assert summary.previous_week_vitesse_kmh == 10.0
    assert summary.evolution_volume_pct == -25.0


def _row(d: date, statut: str, type_seance: str, distance: str = "", temps: str = "", remarques: str = "") -> list:
    return [
        d.strftime("%d/%m/%Y"), str(d.isocalendar()[1]), statut, type_seance, distance,
        "0", distance, temps, "", "", "", "", "", "", "", "", remarques, "",
    ]


def test_sport_connector_get_all_sessions_public_accessor():
    """Le dashboard a besoin de l'historique complet via une méthode publique (copie défensive)."""
    d = date(2026, 10, 5)
    connector = _build_seances_only_connector([
        _row(d, "Réalisé", "EF", "5.0", "00:30:00"),
        _row(d + timedelta(days=1), "Prévu", "Renforcement"),
    ])

    sessions = connector.get_all_sessions()

    assert [s.type_seance for s in sessions] == [SportSessionType.EF, SportSessionType.RENFORCEMENT]
    sessions.clear()
    assert len(connector.get_all_sessions()) == 2  # Le cache interne n'est pas altéré


def test_sport_connector_update_session_targets_type_when_two_sessions_same_day():
    """Avec Renfo + EF le même jour, target_type permet de modifier la bonne ligne."""
    d = date(2026, 10, 6)
    connector = _build_seances_only_connector([
        _row(d, "Réalisé", "Renforcement", "", "00:30:00", "Renfo ok"),
        _row(d, "Réalisé", "EF", "5.0", "00:32:00", "Footing"),
    ])

    updated = connector.update_session(
        d, SportSessionUpdate(ressenti_rpe=6, remarques="tibia sensible", append_remarques=True),
        target_type=SportSessionType.EF,
    )

    assert updated.type_seance == SportSessionType.EF
    assert updated.ressenti_rpe == 6
    assert updated.remarques == "Footing | tibia sensible"
    sessions = connector.get_all_sessions()
    renfo = next(s for s in sessions if s.type_seance == SportSessionType.RENFORCEMENT)
    assert renfo.remarques == "Renfo ok"
    assert renfo.ressenti_rpe is None


def test_sport_connector_update_session_unknown_target_type_raises_explicit_error():
    """Fail-fast : type introuvable à cette date -> message listant les types disponibles."""
    d = date(2026, 10, 6)
    connector = _build_seances_only_connector([_row(d, "Réalisé", "EF", "5.0", "00:30:00")])

    with pytest.raises(ValueError, match=r"Fractionné.*EF"):
        connector.update_session(d, SportSessionUpdate(ressenti_rpe=5), target_type=SportSessionType.FRACTIONNE)




