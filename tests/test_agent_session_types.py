"""Types de séance cités par l'utilisateur, déduits par le code (garde-fou anti-ambiguïté, Phase 6.8 - Étape 5)."""
import pytest

from app.connectors.sheets.sport_models import SportSessionType as T
from app.core.agent.tools.session_types import cited_session_types


@pytest.mark.parametrize("text, expected", [
    ("Mets le RPE de ma séance d'hier à 6.", set()),
    ("Le RPE de ma dernière séance de renfo à 3", {T.RENFORCEMENT}),
    ("je parlais de ma séance de renforcement musculaire", {T.RENFORCEMENT}),
    ("mon footing d'hier", {T.EF}),
    ("l'EF de dimanche", {T.EF}),
    ("c'était une séance de fractionné", {T.FRACTIONNE}),
    ("ma sortie longue et mon gainage", {T.SORTIE_LONGUE, T.RENFORCEMENT}),
    ("une séance de récup", {T.RECUP}),
    ("du tempo puis de la vitesse", {T.TEMPO, T.VITESSE}),
    ("la course d'hier", set()),  # « course » ne désigne pas un type précis
    ("je me sens effondré", set()),  # « ef » seulement comme mot entier
])
def test_cited_session_types(text, expected):
    assert cited_session_types([text]) == expected


def test_types_are_collected_across_several_utterances():
    assert cited_session_types(["Mets le RPE à 3", "non, le renfo"]) == {T.RENFORCEMENT}
