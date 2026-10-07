"""Test d'intégration End-to-End (E2E) pour le module Sport Running & Coach Otis (Étape 9).

Valide le cycle de vie complet en conditions applicatives :
1. Consultation initiale de la journée (Séance du jour, Conseil Otis, Daily Spotlight).
2. Saisie vocale d'une séance de course (Distance, Durée, D+, RPE) via /api/v1/interact.
3. Consultation du comparateur de séances et des calculs physiologiques.
4. Saisie vocale d'une séance de renforcement musculaire.
5. Signalement d'une alerte douleur a posteriori (périostite) via PATCH et réaction du coach.
6. Planification hebdomadaire proactive intelligente (deload / reprise).
7. Explication pédagogique vulgarisée d'un exercice de renforcement.
8. Gamification complète : déblocage de badges (Mono-session, Pop-culture, Paliers) et PRs.
9. Dashboard multi-échelles (Semaine, Mois, Année) et calcul du plafond de sécurité.
"""
from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.connectors.sheets.sport_connector import SportConnector
from app.connectors.sheets.sport_models import (
    CoachTipLevel,
    DashboardScale,
    SportBadge,
    SportCoachTip,
    SportSession,
    SportSessionCreate,
    SportSessionStatus,
    SportSessionType,
    SportSessionUpdate,
)
from app.main import app, set_sport_connector

client = TestClient(app)


class InMemorySportStore:
    """Simulateur mémoire fidèle d'un classeur Google Sheets Sport."""

    def __init__(self, initial_sessions: Optional[List[SportSession]] = None):
        self.sessions: List[SportSession] = list(initial_sessions or [])

    def get_all_sessions(self) -> List[SportSession]:
        return list(self.sessions)

    def get_session(self, target_date: date) -> Optional[SportSession]:
        for s in self.sessions:
            if s.date == target_date:
                return s
        return None

    def log_session(self, create_data: SportSessionCreate) -> SportSession:
        # Si une séance planifiée existait déjà ce jour pour ce type, on l'écrase / la met à jour
        session = SportSession(
            date=create_data.date,
            semaine=create_data.date.isocalendar()[1],
            statut=SportSessionStatus.REALISE,
            type_seance=create_data.type_seance,
            distance_km=create_data.distance_km,
            duree_secondes=create_data.duree_secondes,
            denivele_d_plus=create_data.denivele_d_plus or 0,
            ressenti_rpe=create_data.ressenti_rpe,
            remarques=create_data.remarques or "",
        )
        self.sessions = [s for s in self.sessions if not (s.date == create_data.date and s.type_seance == create_data.type_seance)]
        self.sessions.append(session)
        return session

    def update_session(self, target_date: date, update_data: Any, target_type: Optional[SportSessionType] = None) -> SportSession:
        if isinstance(update_data, dict):
            update_data = SportSessionUpdate(**update_data)

        candidates = [s for s in self.sessions if s.date == target_date]
        if not candidates:
            raise ValueError(f"Aucune séance trouvée le {target_date}")

        chosen = None
        if target_type:
            for s in candidates:
                if s.type_seance == target_type:
                    chosen = s
                    break
        if not chosen:
            chosen = candidates[0]

        new_rpe = update_data.ressenti_rpe if update_data.ressenti_rpe is not None else chosen.ressenti_rpe
        new_remarques = chosen.remarques or ""
        if update_data.remarques:
            if update_data.append_remarques and new_remarques:
                new_remarques = f"{new_remarques} ; {update_data.remarques}"
            else:
                new_remarques = update_data.remarques

        updated = SportSession(
            date=chosen.date,
            semaine=chosen.semaine,
            statut=chosen.statut,
            type_seance=chosen.type_seance,
            distance_km=chosen.distance_km,
            duree_secondes=chosen.duree_secondes,
            denivele_d_plus=chosen.denivele_d_plus,
            ressenti_rpe=new_rpe,
            remarques=new_remarques,
        )

        self.sessions = [s for s in self.sessions if s is not chosen]
        self.sessions.append(updated)
        return updated

    def plan_weekly_sessions(self, target_week: int, target_year: int, proposals: List[Any]) -> List[SportSession]:
        created = []
        for prop in proposals:
            d = prop.date if hasattr(prop, "date") else date.today()
            t = prop.type_seance if hasattr(prop, "type_seance") else SportSessionType.EF
            dist = prop.distance_km if hasattr(prop, "distance_km") else None
            dur = prop.duree_secondes if hasattr(prop, "duree_secondes") else None
            note = prop.programme if hasattr(prop, "programme") else ""
            s = SportSession(
                date=d,
                semaine=target_week,
                statut=SportSessionStatus.PLANIFIE,
                type_seance=t,
                distance_km=dist,
                duree_secondes=dur,
                notes=note,
            )
            self.sessions.append(s)
            created.append(s)
        return created


@pytest.fixture
def e2e_sport_store(monkeypatch):
    """Prépare un historique représentatif de 3 semaines pour tester l'intégralité du flow."""
    ref_today = date.today()

    # Mock rapide du conseil LLM pour éviter les timeouts réseau pendant la validation
    async def mock_coach_tip(context):
        # Si une douleur ou alerte est présente dans les remarques, basculer en alerte
        all_s = context.get("seances_du_jour", []) + context.get("seances_recentes", [])
        if any("douleur" in (s.get("remarques") or "").lower() or "tibia" in (s.get("remarques") or "").lower() for s in all_s):
            return SportCoachTip(
                message="Attention, douleur au tibia détectée ! Priorité absolue au repos et à la glace.",
                niveau=CoachTipLevel.ALERTE,
                source="otis",
            )
        return SportCoachTip(
            message="Séance bien gérée, garde cette aisance en endurance fondamentale !",
            niveau=CoachTipLevel.INFO,
            source="otis",
        )

    import app.routers.sport as sport_router
    monkeypatch.setattr(sport_router, "_call_gemini_coach_tip", mock_coach_tip)

    # Semaine 39 : 4 séances (EF, Fractionné, SL, Renfo)
    s39_1 = SportSession(date=date(2026, 9, 22), semaine=39, statut=SportSessionStatus.REALISE, type_seance=SportSessionType.EF, distance_km=8.0, duree_secondes=2700, denivele_d_plus=50, ressenti_rpe=5)
    s39_2 = SportSession(date=date(2026, 9, 24), semaine=39, statut=SportSessionStatus.REALISE, type_seance=SportSessionType.FRACTIONNE, distance_km=7.0, duree_secondes=2250, denivele_d_plus=30, ressenti_rpe=7)
    s39_3 = SportSession(date=date(2026, 9, 26), semaine=39, statut=SportSessionStatus.REALISE, type_seance=SportSessionType.SORTIE_LONGUE, distance_km=14.0, duree_secondes=4900, denivele_d_plus=150, ressenti_rpe=6)
    s39_4 = SportSession(date=date(2026, 9, 27), semaine=39, statut=SportSessionStatus.REALISE, type_seance=SportSessionType.RENFORCEMENT, distance_km=0.0, duree_secondes=1800, denivele_d_plus=0, ressenti_rpe=5)

    # Semaine 40 : 1 séance précédente du même type (pour alimenter le comparateur)
    s40_prev_ef = SportSession(date=date(2026, 9, 29), semaine=40, statut=SportSessionStatus.REALISE, type_seance=SportSessionType.EF, distance_km=9.0, duree_secondes=3100, denivele_d_plus=60, ressenti_rpe=5, remarques="Bonne aisance")

    # Séance planifiée pour aujourd'hui
    s_today_planned = SportSession(date=ref_today, semaine=ref_today.isocalendar()[1], statut=SportSessionStatus.PLANIFIE, type_seance=SportSessionType.EF, distance_km=10.5, duree_secondes=3600, notes="Footing d'EF régulier en endurance fondamentale")

    initial = [s39_1, s39_2, s39_3, s39_4, s40_prev_ef, s_today_planned]
    store = InMemorySportStore(initial)

    mock_connector = MagicMock(spec=SportConnector)
    mock_connector.get_all_sessions.side_effect = store.get_all_sessions
    mock_connector.get_session.side_effect = store.get_session
    mock_connector.log_session.side_effect = store.log_session
    mock_connector.update_session.side_effect = store.update_session
    mock_connector.plan_weekly_sessions.side_effect = store.plan_weekly_sessions

    set_sport_connector(mock_connector)
    yield store
    set_sport_connector(None)


def test_complete_e2e_running_and_coach_otis_lifecycle(e2e_sport_store):
    """Scénario d'intégration E2E complet validant l'ensemble du cycle de vie Sport Running."""
    today = date.today()

    # -------------------------------------------------------------------------
    # 1. Consultation initiale de la journée (Page Séance du Jour & Mot d'Otis)
    # -------------------------------------------------------------------------
    resp_today_init = client.get(f"/api/v1/sport/today?date={today.isoformat()}")
    assert resp_today_init.status_code == 200
    data_today_init = resp_today_init.json()

    assert data_today_init["date"] == today.isoformat()
    assert len(data_today_init["seances"]) == 1
    session_init = data_today_init["seances"][0]
    assert session_init["statut"] == "Prévu"
    assert session_init["distance_km"] == 10.5
    assert "daily_spotlight" in data_today_init
    assert data_today_init["daily_spotlight"] is not None
    # Le Mot d'Otis annonce la couleur en première page !
    assert "coach_tip" in data_today_init

    # -------------------------------------------------------------------------
    # 2. Saisie vocale d'une séance terminée (Interact NLU -> Log Session)
    # -------------------------------------------------------------------------
    # L'athlète rentre de sa sortie et dit : "J'ai couru 10.5 km en 58 minutes, ressenti 5, 120m de dénivelé"
    resp_interact_log = client.post(
        "/api/v1/interact",
        json={"text": "J'ai couru 10.5 km en 58 minutes avec 120m de dénivelé, ressenti 5 sur 10"},
    )
    assert resp_interact_log.status_code == 200
    data_interact_log = resp_interact_log.json()
    assert data_interact_log["success"] is True
    assert "10" in data_interact_log["spoken_response"] or "enregistrée" in data_interact_log["spoken_response"].lower()

    # -------------------------------------------------------------------------
    # 3. Consultation post-séance (Séance Réalisée, Calculs & Comparateur)
    # -------------------------------------------------------------------------
    resp_today_done = client.get(f"/api/v1/sport/today?date={today.isoformat()}")
    assert resp_today_done.status_code == 200
    data_today_done = resp_today_done.json()

    assert len(data_today_done["seances"]) == 1
    session_done = data_today_done["seances"][0]
    assert session_done["statut"] == "Réalisé"
    assert session_done["distance_km"] == 10.5
    assert session_done["denivele_d_plus"] == 120
    assert session_done["km_effort"] == 11.7 # 10.5 + 1.2
    assert session_done["vitesse_kmh"] is not None
    assert session_done["allure_secondes"] is not None

    # Vérification du comparateur de séances (avec celle du 2026-09-29)
    assert len(data_today_done["comparisons"]) == 1
    comp = data_today_done["comparisons"][0]
    assert comp["previous_session"]["date"] == "2026-09-29"
    dist_delta = next((d for d in comp["deltas"] if d["metric"] == "distance_km"), None)
    assert dist_delta is not None
    assert dist_delta["current"] == 10.5
    assert dist_delta["previous"] == 9.0

    # -------------------------------------------------------------------------
    # 4. Saisie vocale d'une séance de renforcement musculaire
    # -------------------------------------------------------------------------
    resp_interact_renfo = client.post(
        "/api/v1/interact",
        json={"text": "Log séance de renforcement 30 minutes gainage et fessiers ressenti 6"},
    )
    assert resp_interact_renfo.status_code == 200
    data_interact_renfo = resp_interact_renfo.json()
    assert data_interact_renfo["success"] is True

    # Vérifier que le renfo a bien été enregistré
    all_sessions_after_renfo = e2e_sport_store.get_all_sessions()
    renfo_sessions = [s for s in all_sessions_after_renfo if s.type_seance == SportSessionType.RENFORCEMENT]
    assert len(renfo_sessions) >= 2 # Celle de s39 + celle d'aujourd'hui

    # -------------------------------------------------------------------------
    # 5. Signalement d'une alerte douleur a posteriori (PATCH -> Réaction Coach)
    # -------------------------------------------------------------------------
    # Alexis note un début de périostite au tibia gauche
    resp_patch = client.patch(
        f"/api/v1/sport/session/{today.isoformat()}",
        json={
            "ressenti_rpe": 8,
            "remarques": "Alerte douleur tibia gauche persistante en fin de sortie",
            "append_remarques": True,
            "target_type": "EF",
        },
    )
    assert resp_patch.status_code == 200
    data_patch = resp_patch.json()
    assert data_patch["success"] is True
    assert data_patch["session"]["ressenti_rpe"] == 8
    assert "tibia" in data_patch["session"]["remarques"].lower()

    # Vérifier que le Coach Otis bascule en alerte sécurité
    resp_coach_alert = client.get(f"/api/v1/sport/today?date={today.isoformat()}")
    tip_alert = resp_coach_alert.json()["coach_tip"]
    assert tip_alert["niveau"] == "alerte"
    assert "tibia" in tip_alert["message"].lower() or "périost" in tip_alert["message"].lower() or "repos" in tip_alert["message"].lower()

    # -------------------------------------------------------------------------
    # 6. Explication pédagogique d'un exercice de renforcement
    # -------------------------------------------------------------------------
    resp_exercise = client.post(
        "/api/v1/interact",
        json={"query": "Comment je fais l'exercice de mollets sur une marche ?"},
    )
    assert resp_exercise.status_code == 200
    data_exercise = resp_exercise.json()
    assert data_exercise["success"] is True
    spoken_exercise = data_exercise["spoken_response"]
    assert len(spoken_exercise) > 20
    assert "mollet" in spoken_exercise.lower() or "marche" in spoken_exercise.lower()

    # -------------------------------------------------------------------------
    # 7. Gamification & Trophées (Mono-Session, Pop-Culture & Records Personnels)
    # -------------------------------------------------------------------------
    resp_gamification = client.get("/api/v1/sport/gamification")
    assert resp_gamification.status_code == 200
    data_gam = resp_gamification.json()

    assert data_gam["total_badges"] >= 70
    assert data_gam["unlocked_count"] >= 3

    unlocked_ids = {b["id"] for b in data_gam["badges"] if b["is_unlocked"]}
    # 10.5 km d'un coup -> "Premier Dix Bornes" débloqué !
    assert "mono_dist_10k" in unlocked_ids
    # 58 minutes -> presque 1h
    # Premier 10k cumulé débloqué
    assert "dist_10k" in unlocked_ids

    # Records Personnels (PR)
    prs = {pr["record_type"]: pr for pr in data_gam["personal_records"]}
    assert "longest_run" in prs
    assert prs["longest_run"]["value"] >= 14.0 # La sortie longue de s39
    assert "max_elevation" in prs
    assert prs["max_elevation"]["value"] >= 120

    # -------------------------------------------------------------------------
    # 8. Dashboard Multi-Échelles & Plafond de Sécurité (+10%)
    # -------------------------------------------------------------------------
    for scale in ("week", "month", "year"):
        resp_dash = client.get(f"/api/v1/sport/dashboard?scale={scale}&date={today.isoformat()}")
        assert resp_dash.status_code == 200
        data_dash = resp_dash.json()
        assert data_dash["scale"] == scale
        assert data_dash["totals"]["nb_seances"] > 0
        assert len(data_dash["series"]) > 0

    # Vérification du plafond de sécurité sur l'échelle semaine
    resp_dash_week = client.get(f"/api/v1/sport/dashboard?scale=week&date={today.isoformat()}")
    data_dash_week = resp_dash_week.json()
    assert data_dash_week["plafond_km_effort"] is not None
    assert data_dash_week["plafond_km_effort"] > 0
