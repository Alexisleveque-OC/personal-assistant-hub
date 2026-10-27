"""Tests des outils agent ajoutés à l'Étape 3 : planning hebdomadaire (coach) et prise de note."""
from datetime import date

import pytest

from app.connectors.sheets.sport_models import SportPlannedSessionProposal, SportWeeklyPlanProposal
from app.connectors.sqlite.sport_connector import SqlSportConnector
from app.core.agent.tool_registry import ToolRegistry
from app.core.agent.tools.note_tools import note_tool_definitions
from app.core.agent.tools.sport_planning import WeeklyPlanningTool, weekly_planning_tool_definitions
from app.core.agent.tools.sport_tools import SportTools

TODAY = date(2026, 10, 21)  # mercredi de la semaine 43


def _proposal(*seances: SportPlannedSessionProposal) -> SportWeeklyPlanProposal:
    return SportWeeklyPlanProposal(
        semaine=43, annee=2026, analyse_historique="Charge stable.", km_effort_total_prevu=20.0,
        plafond_recommande=22.0, conseil_blessure_periostite="Sol souple.", seances=list(seances),
        spoken_summary="Semaine de consolidation.",
    )


def _seance(day: date, type_seance: str, **extra) -> SportPlannedSessionProposal:
    return SportPlannedSessionProposal(
        jour="x", date_seance=day, type_seance=type_seance, duree_minutes=40, programme=f"Programme {type_seance}", **extra,
    )


class FakeCoach:
    def __init__(self, proposal=None, error: Exception = None):
        self.proposal, self.error, self.calls = proposal, error, []

    async def plan_weekly_training(self, query: str = "", target_week=None, target_year=None):
        self.calls.append((query, target_week, target_year))
        if self.error:
            raise self.error
        return self.proposal


@pytest.fixture
def db(isolate_sqlite_database):
    return isolate_sqlite_database


@pytest.fixture
def sport_tools(db):
    return SportTools(SqlSportConnector(db_manager=db), today=lambda: TODAY)


def _registry(sport_tools, coach) -> ToolRegistry:
    return ToolRegistry(weekly_planning_tool_definitions(WeeklyPlanningTool(sport_tools, coach)))


@pytest.mark.asyncio
async def test_weekly_plan_creates_future_sessions_and_skips_past_or_busy_days(db, sport_tools):
    done = db.add_sport_session({"date": "2026-10-22", "type_seance": "EF", "statut": "Réalisé", "distance_km": 5.0})
    coach = FakeCoach(_proposal(
        _seance(date(2026, 10, 19), "Fractionné"),  # lundi passé
        _seance(date(2026, 10, 22), "Renforcement"),  # jour déjà occupé
        _seance(date(2026, 10, 24), "Sortie Longue", distance_km=9.0, allure_cible="06:30/km", remarques_coach="Sol souple"),
    ))

    execution = await _registry(sport_tools, coach).execute(
        "plan_weekly_training", {"semaine": 43, "consignes": "pas de renfo le jeudi"},
    )

    assert coach.calls == [("pas de renfo le jeudi", 43, None)]
    assert execution.error is None
    created = execution.response["created"]
    assert [(s["date"], s["type_seance"], s["statut"]) for s in created] == [("2026-10-24", "Sortie Longue", "Prévu")]
    assert [(s["date"], s["raison"]) for s in execution.response["skipped"]] == [
        ("2026-10-19", "jour passé"), ("2026-10-22", "jour déjà occupé (EF Réalisé)"),
    ]
    assert execution.response["resume"] == "Semaine de consolidation."
    saturday = db.get_sport_session_by_id(created[0]["id"])
    assert (saturday["distance_km"], saturday["duree_secondes"], saturday["allure_cible"], saturday["remarques"]) == (
        9.0, 2400, "06:30/km", "Sol souple",
    )
    assert db.get_sport_session_by_id(done)["type_seance"] == "EF"
    assert [u.session_id for u in execution.undos] == [created[0]["id"]]


@pytest.mark.asyncio
async def test_weekly_plan_coach_failure_is_returned_as_explicit_error(sport_tools):
    coach = FakeCoach(error=RuntimeError("La planification hebdomadaire nécessite Gemini."))
    execution = await _registry(sport_tools, coach).execute("plan_weekly_training", {})
    assert "nécessite Gemini" in execution.error
    assert execution.undos == []


@pytest.mark.asyncio
async def test_save_note_stores_french_note_in_second_brain(db):
    registry = ToolRegistry(note_tool_definitions(db))
    execution = await registry.execute(
        "save_note", {"content": "Corriger le ciblage des séances", "category": "bug_report", "tags": ["sport"]},
    )
    assert execution.error is None
    note = db.get_note(execution.response["note_id"])
    assert (note["content"], note["category"]) == ("Corriger le ciblage des séances", "bug_report")


@pytest.mark.asyncio
async def test_save_note_rejects_empty_content(db):
    execution = await ToolRegistry(note_tool_definitions(db)).execute("save_note", {"content": "  "})
    assert "content" in execution.error


# --- « Note ces derniers échanges » : résumé du modèle + extrait exact du dernier échange (décision 27/10) ---------

def _history(*texts: str):
    from app.core.agent.agent_service import ConversationTurn

    return [ConversationTurn(role="user" if i % 2 == 0 else "assistant", text=t) for i, t in enumerate(texts)]


async def _save(db, history, **args):
    execution = await ToolRegistry(note_tool_definitions(db, history)).execute("save_note", args)
    assert execution.error is None, execution.error
    return db.get_note(execution.response["note_id"])["content"]


@pytest.mark.asyncio
async def test_note_on_previous_exchange_appends_its_exact_text_under_the_summary(db):
    history = _history(
        "Quelle était ma séance d'hier ?", "Une EF de 5 km.",
        "Et ma dernière renfo ?", "Vendredi 23 octobre, 40 minutes, RPE 5.",
    )

    content = await _save(db, history, content="Réponse sur la renfo à vérifier.", inclure_dernier_echange=True)

    assert content == (
        "Réponse sur la renfo à vérifier.\n\n— Dernier échange —\n"
        "Toi : Et ma dernière renfo ?\nOtis : Vendredi 23 octobre, 40 minutes, RPE 5."
    )


@pytest.mark.asyncio
async def test_note_without_the_flag_keeps_only_the_summary(db):
    content = await _save(db, _history("Question ?", "Réponse."), content="Idée libre.")

    assert content == "Idée libre."


@pytest.mark.asyncio
async def test_note_on_previous_exchange_without_history_keeps_only_the_summary(db):
    content = await _save(db, [], content="Rien avant.", inclure_dernier_echange=True)

    assert content == "Rien avant."
