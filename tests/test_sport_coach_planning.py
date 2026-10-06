"""Tests unitaires pour le Cerveau Coach d'Otis : Planification Hebdomadaire Proactive (Étape 6)."""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.connectors.sheets.sport_connector import SportConnector
from app.connectors.sheets.sport_models import (
    SportPlannedSessionProposal,
    SportSession,
    SportSessionStatus,
    SportSessionType,
    SportWeeklyPlanProposal,
    SportWeeklySummary,
)
from app.core.sport_coach_service import SportCoachService


def test_sport_planned_session_proposal_model():
    """Valide la structure et les types d'une séance proposée."""
    session = SportPlannedSessionProposal(
        jour="Lundi",
        date_seance=date(2026, 10, 12),
        type_seance=SportSessionType.FRACTIONNE,
        distance_km=6.5,
        duree_minutes=45,
        allure_cible="Échauffement 6'00/km + 6x400m à 4'25/km",
        programme="2 km échauffement + 6x400m r=1'15 + 1 km retour au calme",
        remarques_coach="Courir sur piste ou sol régulier, bien s'hydrater.",
    )
    assert session.jour == "Lundi"
    assert session.type_seance == SportSessionType.FRACTIONNE
    assert session.distance_km == 6.5
    assert session.duree_minutes == 45


def test_sport_weekly_plan_proposal_model():
    """Valide le contrat complet d'un plan hebdomadaire proposé par le coach."""
    plan = SportWeeklyPlanProposal(
        semaine=42,
        annee=2026,
        est_semaine_repos=False,
        analyse_historique="Volume stable à 10.1 km en S40 avec bonne tolérance.",
        km_effort_total_prevu=11.0,
        plafond_recommande=11.1,
        respecte_regle_10_pct=True,
        conseil_blessure_periostite="Privilégier les chemins souples en sous-bois et étirements des soléaires.",
        seances=[
            SportPlannedSessionProposal(
                jour="Lundi",
                type_seance=SportSessionType.FRACTIONNE,
                distance_km=4.5,
                duree_minutes=35,
                allure_cible="4'30/km",
                programme="5x300m",
            ),
            SportPlannedSessionProposal(
                jour="Mardi",
                type_seance=SportSessionType.RENFORCEMENT,
                distance_km=None,
                duree_minutes=30,
                programme="PPG kiné mollets et gainage",
            ),
            SportPlannedSessionProposal(
                jour="Jeudi",
                type_seance=SportSessionType.EF,
                distance_km=4.0,
                duree_minutes=25,
                allure_cible="6'10/km",
                programme="Footing régulier",
            ),
            SportPlannedSessionProposal(
                jour="Samedi",
                type_seance=SportSessionType.SORTIE_LONGUE,
                distance_km=7.0,
                duree_minutes=45,
                allure_cible="6'05/km",
                programme="Sortie vallonnée douce",
            ),
        ],
        avis_sur_souhaits_alexis=None,
        spoken_summary="Voici ton plan pour la semaine : 3 courses et 1 renfo pour un total de 15.5 km-effort.",
    )
    assert plan.semaine == 42
    assert len(plan.seances) == 4
    assert plan.respecte_regle_10_pct is True
    assert "soléaires" in plan.conseil_blessure_periostite


@pytest.mark.asyncio
async def test_plan_weekly_training_offline_raises_explicit_error():
    """RÈGLE SUBLIME D'ALEXIS : Pas de mode hors-ligne. Une erreur explicite doit être levée si Gemini n'est pas connecté."""
    connector = MagicMock(spec=SportConnector)
    mock_gemini = MagicMock()
    mock_gemini.is_configured = False

    service = SportCoachService(connector=connector, gemini_client=mock_gemini)

    with pytest.raises(RuntimeError) as exc_info:
        await service.plan_weekly_training(query="Prévois ma semaine d'entraînement")

    err_msg = str(exc_info.value).lower()
    assert "hors-ligne" in err_msg or "connecté" in err_msg or "gemini" in err_msg


@pytest.mark.asyncio
async def test_plan_weekly_training_normal_week_structure_and_paces():
    """Vérifie la génération d'une semaine normale : Lundi fractionné, Mardi renfo, Jeudi EF, Samedi SL."""
    connector = MagicMock(spec=SportConnector)
    connector.get_weekly_summary.return_value = SportWeeklySummary(
        semaine=41,
        annee=2026,
        nb_seances=3,
        km_total=12.0,
        d_plus_total=50,
        km_effort_total=12.5,
        duree_secondes=4500,
        previous_week_km_effort=11.5,
    )
    connector.get_week_sessions.return_value = [
        SportSession(
            date=date(2026, 10, 5),
            semaine=41,
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.EF,
            distance_km=6.0,
            duree_secondes=2160,  # 6'00/km
            remarques="Bonne forme, légère gêne tibia droit",
        )
    ]

    mock_gemini = MagicMock()
    mock_gemini.is_configured = True

    # Réponse simulée du LLM Gemini respectant la structure exigée par Alexis
    fake_plan_data = {
        "semaine": 42,
        "annee": 2026,
        "est_semaine_repos": False,
        "analyse_historique": "Charge précédente de 12.5 km-effort bien assimilée.",
        "km_effort_total_prevu": 13.5,
        "plafond_recommande": 13.75,
        "respecte_regle_10_pct": True,
        "conseil_blessure_periostite": "Courir sur pelouse ou sentier meuble pour limiter les impacts.",
        "seances": [
            {
                "jour": "Lundi",
                "type_seance": "Fractionné",
                "distance_km": 5.0,
                "duree_minutes": 35,
                "allure_cible": "Échauffement 6'00/km, 6x300m à 4'25/km",
                "programme": "2 km échauffement + 6x300m r=100m trot + 1 km retour au calme",
                "remarques_coach": "Piste souple recommandée.",
            },
            {
                "jour": "Mardi",
                "type_seance": "Renforcement",
                "distance_km": None,
                "duree_minutes": 30,
                "allure_cible": None,
                "programme": "Renforcement kiné : mollets excentriques, soléaires et gainage planche",
                "remarques_coach": "Sans impact, focus chaîne postérieure.",
            },
            {
                "jour": "Jeudi",
                "type_seance": "EF",
                "distance_km": 5.0,
                "duree_minutes": 31,
                "allure_cible": "6'10/km",
                "programme": "Footing endurance fondamentale très relâché",
                "remarques_coach": "Terrain souple en sous-bois.",
            },
            {
                "jour": "Samedi",
                "type_seance": "Sortie Longue",
                "distance_km": 8.0,
                "duree_minutes": 48,
                "allure_cible": "6'00/km",
                "programme": "Sortie longue allure stable",
                "remarques_coach": "Hydratation régulière.",
            },
        ],
        "avis_sur_souhaits_alexis": None,
        "spoken_summary": "Alexis, voici ton plan pour la semaine : fractionné lundi, renfo mardi, EF jeudi et sortie longue samedi.",
    }

    service = SportCoachService(connector=connector, gemini_client=mock_gemini)

    with patch.object(service, "_call_gemini_coach", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = SportWeeklyPlanProposal(**fake_plan_data)
        plan = await service.plan_weekly_training(query="Otis, prévois-moi ma semaine d'entraînement")

    assert plan.semaine == 42
    assert plan.est_semaine_repos is False
    assert len(plan.seances) == 4
    jours = [s.jour for s in plan.seances]
    assert jours == ["Lundi", "Mardi", "Jeudi", "Samedi"]
    types = [s.type_seance for s in plan.seances]
    assert types == [
        SportSessionType.FRACTIONNE,
        SportSessionType.RENFORCEMENT,
        SportSessionType.EF,
        SportSessionType.SORTIE_LONGUE,
    ]
    assert "mollets" in plan.seances[1].programme.lower()
    assert plan.respecte_regle_10_pct is True


@pytest.mark.asyncio
async def test_plan_weekly_training_rest_week_structure():
    """Vérifie la génération d'une semaine de repos : Mardi renfo étirements, Jeudi EF 30 min, Samedi SL allégée."""
    connector = MagicMock(spec=SportConnector)
    connector.get_weekly_summary.return_value = SportWeeklySummary(
        semaine=41,
        annee=2026,
        nb_seances=4,
        km_total=25.0,
        d_plus_total=100,
        km_effort_total=26.0,
        duree_secondes=9000,
    )
    connector.get_week_sessions.return_value = []

    mock_gemini = MagicMock()
    mock_gemini.is_configured = True

    fake_deload_data = {
        "semaine": 42,
        "annee": 2026,
        "est_semaine_repos": True,
        "analyse_historique": "Gros volume en S41 (26 km-effort), semaine de décharge nécessaire.",
        "km_effort_total_prevu": 12.0,
        "plafond_recommande": 28.6,
        "respecte_regle_10_pct": True,
        "conseil_blessure_periostite": "Semaine d'assimilation : beaucoup d'étirements et massage du périoste.",
        "seances": [
            {
                "jour": "Mardi",
                "type_seance": "Renforcement",
                "distance_km": None,
                "duree_minutes": 30,
                "allure_cible": None,
                "programme": "Mobilité et étirements complets : mollets, ischios, fessiers",
                "remarques_coach": "Aucun saut ni impact.",
            },
            {
                "jour": "Jeudi",
                "type_seance": "EF",
                "distance_km": 4.5,
                "duree_minutes": 30,
                "allure_cible": "6'20/km",
                "programme": "Footing court de récupération active d'environ 30 minutes",
                "remarques_coach": "Très cool, fréquence cardiaque basse.",
            },
            {
                "jour": "Samedi",
                "type_seance": "Sortie Longue",
                "distance_km": 7.5,
                "duree_minutes": 48,
                "allure_cible": "6'15/km",
                "programme": "Sortie longue allégée en endurance",
                "remarques_coach": "Terminer avec 10 min de marche et glace.",
            },
        ],
        "avis_sur_souhaits_alexis": "Semaine allégée prise en compte pour régénérer le corps.",
        "spoken_summary": "Semaine de repos au programme : renfo étirements mardi, EF de 30 min jeudi et sortie longue allégée samedi.",
    }

    service = SportCoachService(connector=connector, gemini_client=mock_gemini)

    with patch.object(service, "_call_gemini_coach", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = SportWeeklyPlanProposal(**fake_deload_data)
        plan = await service.plan_weekly_training(query="Otis, prévois une semaine allégée de repos")

    assert plan.est_semaine_repos is True
    assert len(plan.seances) == 3
    jours = [s.jour for s in plan.seances]
    assert jours == ["Mardi", "Jeudi", "Samedi"]
    assert "étirement" in plan.seances[0].programme.lower()
    assert plan.seances[1].duree_minutes == 30


@pytest.mark.asyncio
async def test_plan_weekly_training_integrates_user_wishes_and_provides_advice():
    """Vérifie qu'Otis analyse le souhait d'Alexis (ex: 15km samedi) et donne son conseil de coach."""
    connector = MagicMock(spec=SportConnector)
    connector.get_weekly_summary.return_value = SportWeeklySummary(
        semaine=41,
        annee=2026,
        nb_seances=3,
        km_total=10.0,
        km_effort_total=10.0,
        duree_secondes=3600,
    )
    connector.get_week_sessions.return_value = []

    mock_gemini = MagicMock()
    mock_gemini.is_configured = True

    fake_advice_data = {
        "semaine": 42,
        "annee": 2026,
        "est_semaine_repos": False,
        "analyse_historique": "Volume précédent de 10 km.",
        "km_effort_total_prevu": 16.0,
        "plafond_recommande": 11.0,
        "respecte_regle_10_pct": False,
        "conseil_blessure_periostite": "Attention au pic brutal de volume.",
        "seances": [
            {
                "jour": "Lundi",
                "type_seance": "Fractionné",
                "distance_km": 4.0,
                "duree_minutes": 30,
                "programme": "4x300m",
            },
            {
                "jour": "Mardi",
                "type_seance": "Renforcement",
                "distance_km": None,
                "duree_minutes": 30,
                "programme": "Kiné mollets",
            },
            {
                "jour": "Jeudi",
                "type_seance": "EF",
                "distance_km": 4.0,
                "duree_minutes": 25,
                "programme": "EF souple",
            },
            {
                "jour": "Samedi",
                "type_seance": "Sortie Longue",
                "distance_km": 15.0,
                "duree_minutes": 90,
                "programme": "Sortie longue demandée par Alexis",
                "remarques_coach": "Surveiller les tibias à la moindre douleur.",
            },
        ],
        "avis_sur_souhaits_alexis": "J'ai intégré tes 15 km samedi comme demandé, mais attention : cela dépasse le plafond conseillé (+10%), reste très vigilant sur tes tibias.",
        "spoken_summary": "J'ai programmé tes 15 km samedi, mais sois prudent avec tes tibias car le volume augmente vite.",
    }

    service = SportCoachService(connector=connector, gemini_client=mock_gemini)

    with patch.object(service, "_call_gemini_coach", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = SportWeeklyPlanProposal(**fake_advice_data)
        plan = await service.plan_weekly_training(query="Otis, je voudrais faire 15 km samedi, prévois ma semaine")

    assert plan.avis_sur_souhaits_alexis is not None
    assert "15 km" in plan.avis_sur_souhaits_alexis
    assert plan.seances[3].distance_km == 15.0


def test_sport_coach_prompt_contains_alexis_fine_tuned_rules():
    """Vérifie que le prompt système d'Otis contient les règles affinées : EF 30-35 min, SL ~1h, allures +/-, et décision repos sur RPE/douleurs."""
    from app.core.sport_coach_service import SPORT_COACH_SYSTEM_PROMPT

    prompt_lower = SPORT_COACH_SYSTEM_PROMPT.lower()
    # Règle EF 30-35 min
    assert "30" in prompt_lower and "35" in prompt_lower
    assert "fondamentale" in prompt_lower
    # Règle SL ~1h
    assert "1h" in prompt_lower or "1 heure" in prompt_lower or "60 minutes" in prompt_lower
    # Règle allure cible +/-
    assert "+/-" in prompt_lower or "marge" in prompt_lower
    # Décision repos basée sur RPE et douleurs
    assert "rpe" in prompt_lower
    assert "douleur" in prompt_lower or "périostite" in prompt_lower


@pytest.mark.asyncio
async def test_plan_weekly_training_injects_pain_and_rpe_alerts_in_prompt():
    """Vérifie que SportCoachService détecte les douleurs et RPE élevés dans les dernières séances et les transmet à Gemini."""
    connector = MagicMock(spec=SportConnector)
    connector.get_weekly_summary.return_value = SportWeeklySummary(
        semaine=40,
        annee=2026,
        nb_seances=3,
        km_total=18.0,
        km_effort_total=19.0,
        duree_secondes=6000,
    )
    connector.get_week_sessions.return_value = [
        SportSession(
            date=date(2026, 10, 4),
            semaine=40,
            statut=SportSessionStatus.REALISE,
            type_seance=SportSessionType.SORTIE_LONGUE,
            distance_km=10.0,
            duree_secondes=3600,
            ressenti_rpe=9,
            remarques="Douleur vive périostite tibia gauche à la fin",
        )
    ]

    mock_gemini = MagicMock()
    mock_gemini.is_configured = True

    service = SportCoachService(connector=connector, gemini_client=mock_gemini)

    fake_plan = SportWeeklyPlanProposal(
        semaine=41,
        annee=2026,
        est_semaine_repos=True,
        analyse_historique="RPE 9 et douleur périostite détectée, semaine de repos impérative.",
        km_effort_total_prevu=10.0,
        plafond_recommande=20.0,
        respecte_regle_10_pct=True,
        conseil_blessure_periostite="Glace et repos actif.",
        seances=[
            SportPlannedSessionProposal(jour="Mardi", type_seance=SportSessionType.RENFORCEMENT, duree_minutes=30, programme="Étirements doux"),
            SportPlannedSessionProposal(jour="Jeudi", type_seance=SportSessionType.EF, distance_km=4.5, duree_minutes=30, programme="EF 30 min"),
            SportPlannedSessionProposal(jour="Samedi", type_seance=SportSessionType.SORTIE_LONGUE, distance_km=7.0, duree_minutes=45, programme="SL douce"),
        ],
        spoken_summary="Repos cette semaine en raison de ta douleur au tibia et du RPE 9.",
    )

    with patch.object(service, "_call_gemini_coach", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = fake_plan
        plan = await service.plan_weekly_training(query="Otis, prévois ma semaine")

        assert mock_call.called
        call_args = mock_call.call_args[0]
        user_prompt_sent = call_args[1]
        assert "douleur" in user_prompt_sent.lower() or "périostite" in user_prompt_sent.lower()
    assert plan.est_semaine_repos is True


@pytest.mark.asyncio
async def test_sport_coach_planning_ensures_target_speed_and_detects_rpe_surge():
    """Vérifie que SportCoachService calcule la vitesse cible manquante et injecte l'alerte de surcharge RPE."""
    connector = MagicMock(spec=SportConnector)
    # Simulation S40 avec explosion RPE (+34.5%)
    summary_s40 = SportWeeklySummary(
        semaine=40,
        annee=2026,
        nb_seances=4,
        km_total=20.42,
        d_plus_total=130,
        km_effort_total=21.72,
        duree_secondes=9905,
        charge_rpe_totale=1154,
        previous_week_km_effort=21.33,
        previous_week_vitesse_kmh=7.11,
        previous_week_charge_rpe=858,
    )
    connector.get_weekly_summary.side_effect = lambda w, y: summary_s40 if w == 40 else None
    connector.get_week_sessions.return_value = []

    mock_gemini = MagicMock()
    mock_gemini.is_configured = True
    service = SportCoachService(connector=connector, gemini_client=mock_gemini)

    fake_plan = SportWeeklyPlanProposal(
        semaine=41,
        annee=2026,
        est_semaine_repos=True,
        analyse_historique="Surcharge RPE détectée en S40.",
        km_effort_total_prevu=15.0,
        plafond_recommande=23.8,
        respecte_regle_10_pct=True,
        conseil_blessure_periostite="Repos et soins mollets.",
        seances=[
            SportPlannedSessionProposal(
                jour="Jeudi",
                type_seance=SportSessionType.EF,
                distance_km=4.5,
                duree_minutes=30,
                allure_cible="06:30/km (+/- 15s)",
                vitesse_cible=None,  # Doit être complétée automatiquement par le service
                programme="EF souple",
            )
        ],
        spoken_summary="Semaine allégée suite à la charge de la semaine dernière.",
    )

    with patch.object(service, "_call_gemini_coach", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = fake_plan
        plan = await service.plan_weekly_training(query="Prévois ma semaine", target_week=41, target_year=2026)

        call_args = mock_call.call_args[0]
        user_prompt_sent = call_args[1]
        assert "surcharge rpe" in user_prompt_sent.lower() or "1154" in user_prompt_sent

    # Vérification que vitesse_cible a été automatiquement calculée à partir de 06:30/km
    assert plan.seances[0].vitesse_cible is not None
    assert "9.2" in plan.seances[0].vitesse_cible


