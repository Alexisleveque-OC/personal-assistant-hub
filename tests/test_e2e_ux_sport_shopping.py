"""Test d'intégration End-to-End (E2E) pour la Phase 5 ter : Retours d'Expérience (Sport & Courses).

Valide le flux complet applicatif de bout en bout :
1. Courses : Synchronisation directe en lot sur 'J'ai fini' et réinitialisation de semaine ('Reset') dans Google Sheets.
2. Sport : Consultation de l'historique chronologique des séances avec filtres multiples et calculs physiologiques.
3. Sport : Consultation des synthèses hebdomadaires avec séances imbriquées et alertes de progression.
"""
from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.core.dependencies import set_meals_connector, set_sport_connector
from app.connectors.sheets.sport_models import (
    SportSession,
    SportSessionStatus,
    SportSessionType,
    SportWeeklySummary,
)
from app.connectors.sheets.sport_connector import SportConnector

client = TestClient(app)


def _get_auth_headers():
    return {"X-API-Key": settings.api_key} if settings.api_key else {}


# ==============================================================================
# 1. FLUX E2E COURSES (SHOPPING BATCH COMPLETE & RESET)
# ==============================================================================

def test_e2e_shopping_batch_sync_and_reset_flow():
    """Valide de bout en bout le flux de courses : coche locale, batch sync sur 'J'ai fini' et reset."""
    mock_meals = MagicMock()
    mock_meals.mark_current_week_items_bought.return_value = 2
    mock_meals.mark_shopping_items_bought.return_value = 1
    mock_meals.uncheck_current_week_items.return_value = 5
    set_meals_connector(mock_meals)

    headers = _get_auth_headers()

    # Étape 1 : Alexis finit ses courses et clique sur "🏁 J'ai fini !"
    complete_payload = {
        "current_week_items": ["Bananes", "Flocons d'avoine"],
        "waiting_list_items": ["Dentifrice"],
    }
    res_complete = client.post("/api/v1/meals/shopping/complete", json=complete_payload, headers=headers)
    assert res_complete.status_code == 200
    data_complete = res_complete.json()
    assert data_complete["success"] is True
    assert data_complete["updated_current_week"] == 2
    assert data_complete["updated_waiting_list"] == 1
    mock_meals.mark_current_week_items_bought.assert_called_once_with(["Bananes", "Flocons d'avoine"])
    mock_meals.mark_shopping_items_bought.assert_called_once_with(["Dentifrice"])

    # Étape 2 : Le samedi suivant, Alexis clique sur "🔄 Réinitialiser" pour débuter une nouvelle semaine
    res_reset = client.post("/api/v1/meals/shopping/reset", headers=headers)
    assert res_reset.status_code == 200
    data_reset = res_reset.json()
    assert data_reset["success"] is True
    assert data_reset["uncheked_count"] == 5
    mock_meals.uncheck_current_week_items.assert_called_once()


# ==============================================================================
# 2. FLUX E2E SPORT SÉANCES & SYNTHÈSES HEBDOMADAIRES
# ==============================================================================

def _build_e2e_sport_dataset():
    """Construit un jeu de données complet de séances réelles pour le test E2E."""
    base = date(2026, 10, 1)  # S40
    sessions = [
        SportSession(
            date=base,
            semaine=40,
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.EF,
            distance_km=10.0,
            duree_secondes=3600,
            denivele_d_plus=50,
            ressenti_rpe=6,
            fc_moyenne=142,
            programme="Endurance fondamentale 10 km",
            remarques="Bonne aisance respiratoire",
        ),
        SportSession(
            date=base + timedelta(days=2),
            semaine=40,
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.VITESSE,
            distance_km=6.0,
            duree_secondes=1920,
            denivele_d_plus=10,
            ressenti_rpe=8,
            programme="Lignes droites et vitesse 6 km",
            remarques="Légère tension au mollet droit",
        ),
        SportSession(
            date=base + timedelta(days=4),
            semaine=40,
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.RENFORCEMENT,
            distance_km=None,
            duree_secondes=1800,
            ressenti_rpe=7,
            programme="Gainage et renforcement mollets",
            remarques="Travail préventif périostite",
        ),
        SportSession(
            date=base + timedelta(days=7),  # 8 oct 2026 -> S41
            semaine=41,
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.COURSE,
            distance_km=12.0,
            duree_secondes=4320,
            denivele_d_plus=120,
            ressenti_rpe=7,
            programme="Sortie tempo vallonnée",
        ),
        SportSession(
            date=base + timedelta(days=9),  # 10 oct 2026 -> S41
            semaine=41,
            statut=SportSessionStatus.PLANIFIE,
            type_seance=SportSessionType.SORTIE_LONGUE,
            distance_km=15.0,
            duree_secondes=5400,
            denivele_d_plus=150,
            programme="Sortie longue souple",
        ),
    ]
    return sessions


def test_e2e_sport_sessions_and_summaries_flow():
    """Valide de bout en bout l'interrogation de l'historique des séances et des synthèses de semaines."""
    mock_sport = MagicMock()
    sample_sessions = _build_e2e_sport_dataset()
    mock_sport.get_all_sessions.return_value = sample_sessions

    # Synthèses de test pour S40 et S41
    sum_s41 = SportWeeklySummary(
        semaine=41,
        annee=2026,
        nb_seances=2,
        km_total=27.0,
        d_plus_total=270,
        km_effort_total=29.7,
        duree_secondes=9720,
        charge_rpe_totale=500,
        alerte_securite="🟢 Progression Saine (+8.2%)",
    )
    sum_s40 = SportWeeklySummary(
        semaine=40,
        annee=2026,
        nb_seances=3,
        km_total=16.0,
        d_plus_total=60,
        km_effort_total=16.6,
        duree_secondes=7320,
        charge_rpe_totale=720,
        alerte_securite="⚪ Première semaine enregistrée",
    )
    mock_sport.get_all_summaries.return_value = [sum_s41, sum_s40]

    # Séances imbriquées pour chaque semaine
    def mock_get_week_sessions(week_num, year=None):
        return [s for s in sample_sessions if s.semaine == week_num]

    mock_sport.get_week_sessions.side_effect = mock_get_week_sessions
    set_sport_connector(mock_sport)

    headers = _get_auth_headers()

    # 1. Récupération globale des séances : tri antichronologique
    res_sessions = client.get("/api/v1/sport/sessions", headers=headers)
    assert res_sessions.status_code == 200
    data_sessions = res_sessions.json()
    assert data_sessions["total"] == 5
    sessions_list = data_sessions["sessions"]
    # Vérifier l'ordre antichronologique : la séance du 10 oct vient en premier, celle du 1er oct en dernier
    assert sessions_list[0]["date"] == "2026-10-10"
    assert sessions_list[-1]["date"] == "2026-10-01"

    # Vérifier les calculs physiologiques
    first_session = sessions_list[-1]  # 1er oct : 10 km, 50m D+, 3600s
    assert first_session["km_effort"] == 10.5
    assert first_session["allure_formatted"] == "06:00"
    assert first_session["vitesse_kmh"] == 10.0
    assert first_session["charge_rpe"] == 360

    # 2. Filtrage par statut Réalisé
    res_realise = client.get("/api/v1/sport/sessions?statut=Réalisé", headers=headers)
    assert res_realise.status_code == 200
    assert res_realise.json()["total"] == 4
    assert all(s["statut"] == "Réalisé" for s in res_realise.json()["sessions"])

    # 3. Filtrage par type : Vitesse et Course
    res_vitesse = client.get("/api/v1/sport/sessions?type_seance=Vitesse", headers=headers)
    assert res_vitesse.status_code == 200
    data_vit = res_vitesse.json()
    assert data_vit["total"] == 1
    assert data_vit["sessions"][0]["type_seance"] == "Vitesse"

    res_course = client.get("/api/v1/sport/sessions?type_seance=Course", headers=headers)
    assert res_course.status_code == 200
    data_course = res_course.json()
    assert data_course["total"] == 1
    assert data_course["sessions"][0]["type_seance"] == "Course"

    # 4. Synthèses de semaines avec séances imbriquées pour l'accordéon
    res_summaries = client.get("/api/v1/sport/summaries?include_sessions=true", headers=headers)
    assert res_summaries.status_code == 200
    data_summaries = res_summaries.json()
    assert data_summaries["total"] == 2
    summaries = data_summaries["summaries"]

    # Semaine 41
    s41_item = summaries[0]
    assert s41_item["summary"]["semaine"] == 41
    assert len(s41_item["seances"]) == 2
    assert s41_item["seances"][0]["type_seance"] in ("Course", "Sortie Longue")

    # Semaine 40
    s40_item = summaries[1]
    assert s40_item["summary"]["semaine"] == 40
    assert len(s40_item["seances"]) == 3
