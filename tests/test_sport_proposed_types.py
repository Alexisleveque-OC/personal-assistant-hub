"""Refonte UX (décision du 10/11) : types proposés pour les nouvelles séances = EF, Course, Sortie Longue, Vitesse,
Fractionné, Renforcement. Tempo et Récup ne sont plus proposés (formulaire, Otis, coach) ; les séances existantes
de ces types restent lisibles et recherchables."""
from datetime import date

import pytest
from pydantic import ValidationError

from app.connectors.sheets.sport_models import ProposedSessionType, SportSessionType
from app.core.agent.fast_reply import _details
from app.core.agent.tools.sport_models import FindSessionsArgs, LogSessionArgs, PlanSessionArgs, SessionChanges
from app.core.sport_coach_service import GEMINI_WEEKLY_PLAN_SCHEMA

PROPOSED = ["EF", "Course", "Sortie Longue", "Vitesse", "Fractionné", "Renforcement"]


def test_proposed_types_are_the_six_kept_by_the_user():
    assert [t.value for t in ProposedSessionType] == PROPOSED
    assert all(SportSessionType(v) for v in PROPOSED)  # même valeurs que les types stockés


@pytest.mark.parametrize("old_type", ["Tempo", "Récup"])
def test_otis_can_no_longer_create_or_retype_a_session_as_tempo_or_recup(old_type):
    with pytest.raises(ValidationError):
        LogSessionArgs(date=date(2026, 11, 9), type_seance=old_type)
    with pytest.raises(ValidationError):
        PlanSessionArgs(date=date(2026, 11, 12), type_seance=old_type)
    with pytest.raises(ValidationError):
        SessionChanges(type_seance=old_type)
    assert FindSessionsArgs(type_seance=old_type).type_seance == SportSessionType(old_type)


def test_tool_schemas_sent_to_gemini_list_only_the_proposed_types():
    for model in (LogSessionArgs, PlanSessionArgs):
        schema = model.model_json_schema()
        enum = schema["$defs"]["ProposedSessionType"]["enum"]
        assert enum == PROPOSED


def test_weekly_coach_plans_only_with_proposed_types():
    enum = GEMINI_WEEKLY_PLAN_SCHEMA["properties"]["seances"]["items"]["properties"]["type_seance"]["enum"]
    assert sorted(enum) == sorted(PROPOSED)


def test_otis_quick_reply_mentions_the_pain():
    assert _details({"douleur_intensite": 4, "douleur_zone": "genou"}) == ["douleur 4/10", "zone genou"]
