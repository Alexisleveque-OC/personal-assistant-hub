"""Réponse directe sans 2e appel Gemini après une modification simple (Étape 7, décision du 27/10/2026).

Périmètre : séance modifiée, enregistrée ou planifiée ; articles ajoutés, cochés ou retirés ; note enregistrée.
Gemini garde la main pour les lectures, le plan de la semaine, les repas, les erreurs, les rayons à demander et
les demandes composées (« et », « puis », « aussi », « ensuite »).
"""
import pytest

from app.core.agent.fast_reply import fast_reply
from app.core.agent.tool_registry import ToolExecution


def _session(**overrides) -> dict:
    session = {"id": 7, "date": "2026-10-23", "jour": "vendredi", "statut": "Réalisé", "type_seance": "Renforcement"}
    return {**session, **overrides}


def _exec(name: str, args: dict, response: dict, error: str = None) -> ToolExecution:
    return ToolExecution(name=name, args=args, response=response, error=error)


def _update(changes: dict, **session) -> ToolExecution:
    return _exec("update_sport_session", {"session_id": 7, "changes": changes},
                 {"action": "updated", "session": _session(**session)})


@pytest.mark.parametrize("changes, expected", [
    ({"ressenti_rpe": 4}, "C'est noté : RPE 4 pour ta renfo du vendredi 23/10."),
    ({"duree_secondes": 2100, "distance_km": 5.5}, "C'est noté : 35 min, 5.5 km pour ta renfo du vendredi 23/10."),
    ({"fc_moyenne": 142, "remarques": "Tibias sensibles"},
     "C'est noté : FC moyenne 142, remarque ajoutée pour ta renfo du vendredi 23/10."),
])
def test_session_update_reply(changes, expected):
    assert fast_reply("Mets le RPE de ma renfo d'hier à 4", [_update(changes)]) == expected


@pytest.mark.parametrize("session_type, expected", [
    ("EF", "pour ton footing"), ("Fractionné", "pour ton fractionné"), ("Sortie Longue", "pour ta sortie longue"),
    ("Tempo", "pour ton tempo"), ("Récup", "pour ton footing de récup"),
])
def test_session_update_uses_the_right_possessive(session_type, expected):
    assert expected in fast_reply("Mets RPE 4", [_update({"ressenti_rpe": 4}, type_seance=session_type)])


def test_logged_and_planned_sessions_reply():
    logged = _exec(
        "log_sport_session",
        {"date": "2026-10-27", "type_seance": "EF", "duree_secondes": 2100, "ressenti_rpe": 4},
        {"action": "created", "session": _session(date="2026-10-27", jour="mardi", type_seance="EF")},
    )
    planned = _exec(
        "plan_sport_session",
        {"date": "2026-10-29", "type_seance": "Sortie Longue", "distance_km": 12.0},
        {"action": "created", "session": _session(date="2026-10-29", jour="jeudi", type_seance="Sortie Longue")},
    )

    assert fast_reply("J'ai fait 35 min de footing, RPE 4", [logged]) == (
        "C'est enregistré : footing du mardi 27/10, 35 min, RPE 4."
    )
    assert fast_reply("Prévois une sortie longue de 12 km jeudi", [planned]) == (
        "C'est planifié : sortie longue le jeudi 29/10, 12 km."
    )


def test_shopping_and_note_replies():
    added = _exec("add_shopping_items", {}, {"ajoutes": [{"nom": "Lait"}], "rayon_a_demander": []})
    checked = _exec("check_shopping_items", {}, {"modifies": ["Lait"], "deja_dans_cet_etat": ["Pain"],
                                                 "introuvables": [], "coche": True})
    unchecked = _exec("check_shopping_items", {}, {"modifies": ["Lait"], "deja_dans_cet_etat": [],
                                                   "introuvables": [], "coche": False})
    removed = _exec("remove_shopping_items", {}, {"retires": ["Lait", "Pain"], "introuvables": [], "remarque": None})
    note = _exec("save_note", {}, {"note_id": 3, "category": "bug_report", "content": "Bug"})

    assert fast_reply("Ajoute du lait", [added]) == "J'ai ajouté Lait à la liste de courses."
    assert fast_reply("Coche le lait", [checked]) == "C'est coché : Lait, Pain."
    assert fast_reply("Décoche le lait", [unchecked]) == "C'est décoché : Lait."
    assert fast_reply("Retire le lait", [removed]) == "J'ai retiré Lait et Pain de la liste de courses."
    assert fast_reply("Note ce bug", [note]) == "C'est noté dans tes bugs."


def test_several_simple_mutations_in_one_turn_are_chained():
    reply = fast_reply("Mets RPE 4 à ma renfo, c'est bon", [_update({"ressenti_rpe": 4}),
                                                          _exec("save_note", {}, {"note_id": 1, "category": "task"})])

    assert reply == "C'est noté : RPE 4 pour ta renfo du vendredi 23/10. C'est noté dans tes tâches."


@pytest.mark.parametrize("query", [
    "Mets le RPE à 4 et note que j'avais mal",
    "Passe le RPE à 4 puis ajoute du lait",
    "Mets aussi le RPE à 4",
    "Ensuite mets le RPE à 4",
])
def test_composite_requests_keep_gemini(query):
    assert fast_reply(query, [_update({"ressenti_rpe": 4})]) is None


@pytest.mark.parametrize("execution", [
    _exec("find_sport_sessions", {}, {"sessions": []}),
    _exec("plan_weekly_training", {}, {"semaine": 44}),
    _exec("set_meal", {}, {"jour": "lundi"}),
    _exec("undo_last_action", {}, {"restored": []}),
    _exec("update_sport_session", {}, {"error": "Séance introuvable"}, error="Séance introuvable"),
    _exec("add_shopping_items", {}, {"ajoutes": [{"nom": "Lait"}], "rayon_a_demander": ["Bougies"]}),
    _exec("check_shopping_items", {}, {"modifies": [], "deja_dans_cet_etat": [], "introuvables": ["Kiwi"], "coche": True}),
    _exec("remove_shopping_items", {}, {"retires": [], "introuvables": [], "remarque": "Liste vide"}),
])
def test_other_tools_errors_and_incomplete_results_keep_gemini(execution):
    assert fast_reply("Fais-le", [execution]) is None


def test_a_turn_mixing_simple_and_other_tools_keeps_gemini():
    assert fast_reply("Mets RPE 4", [_update({"ressenti_rpe": 4}), _exec("set_meal", {}, {})]) is None
    assert fast_reply("Mets RPE 4", []) is None
