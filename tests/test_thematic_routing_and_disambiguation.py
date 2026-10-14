"""Tests unitaires TDD pour le Routage Thématique Contextuel et la Désambiguïsation (Étape 3).

Valide que les intentions explicites de prise de note (Second Cerveau), de tâches et de courses
ne soient JAMAIS interceptées à tort par le module Sport, même en présence de termes sportifs
ou de chiffres ambigus.
"""
import pytest
from app.core.intent_parser import IntentParser
from app.core.models import IntentType, NoteCategory

parser = IntentParser()


def test_alexis_multi_turn_note_never_triggers_sport_mutation():
    """Vérifie le cas soulevé par Alexis : 'Ok prends note de ces 3 derniers échanges. Il faut corriger'."""
    fake_context = {
        "history": [
            {"role": "user", "text": "Le bouton de validation ne répond pas"},
            {"role": "assistant", "text": "Je vérifie les logs"},
        ]
    }
    res = parser.parse("Ok prends note de ces 3 derniers échanges. Il faut corriger", context=fake_context)
    assert res.intent == IntentType.SAVE_NOTE
    assert res.intent != IntentType.UPDATE_SPORT_SESSION
    assert res.intent != IntentType.LOG_SPORT_SESSION
    assert res.parameters.get("category") == NoteCategory.BUG_REPORT.value
    assert "corriger" in res.parameters.get("content", "").lower()


@pytest.mark.parametrize(
    "phrase,expected_category",
    [
        ("Prends note pour ma séance de course : penser à tester les nouvelles chaussures", NoteCategory.THOUGHT.value),
        ("Note pour la séance de renfo : faire 3 séries de gainage", NoteCategory.THOUGHT.value),
        ("Note de bug : la modification de séance de course ne marche pas", NoteCategory.BUG_REPORT.value),
        ("Idée dev : ajouter un mode sombre sur la page sport", NoteCategory.DEV_IDEA.value),
        ("Idée de code : calculer la fréquence cardiaque de réserve", NoteCategory.DEV_IDEA.value),
        ("Prends note : hier j'ai eu une idée pour courir plus vite", NoteCategory.THOUGHT.value),
        ("Note que pour le prochain footing de 10km je dois prendre de l'eau", NoteCategory.THOUGHT.value),
        ("À noter : la séance de fractionné est reportée à demain", NoteCategory.THOUGHT.value),
        ("Pense-bête : bien étirer le mollet après ma séance", NoteCategory.THOUGHT.value),
        ("Ajoute une note : vérifier l'allure sur la sortie longue", NoteCategory.THOUGHT.value),
        ("Enregistre une note : bug sur la saisie de FC max", NoteCategory.BUG_REPORT.value),
    ],
)
def test_explicit_notes_with_sport_terms_never_trigger_sport_intents(phrase, expected_category):
    """Vérifie qu'une intention explicite de note avec vocabulaire sportif reste strictement une note."""
    res = parser.parse(phrase)
    assert res.intent == IntentType.SAVE_NOTE
    assert res.intent not in (
        IntentType.UPDATE_SPORT_SESSION,
        IntentType.LOG_SPORT_SESSION,
        IntentType.GET_SPORT_SESSION,
        IntentType.PLAN_SPORT_SESSION,
    )
    if expected_category:
        assert res.parameters.get("category") == expected_category


def test_note_update_or_delete_never_confused_with_sport_update():
    """Vérifie que 'mets à jour la note' ou 'supprime la note' ne modifie pas une séance de sport."""
    res1 = parser.parse("Mets à jour la note 3")
    assert res1.intent != IntentType.UPDATE_SPORT_SESSION

    res2 = parser.parse("Mets à jour la note sur le projet de course")
    assert res2.intent != IntentType.UPDATE_SPORT_SESSION

    res3 = parser.parse("Supprime la note 5")
    assert res3.intent == IntentType.DELETE_NOTE
    assert res3.intent != IntentType.UPDATE_SPORT_SESSION


def test_shopping_and_tasks_with_sport_terms_route_correctly():
    """Vérifie que les courses et tâches mentionnant du sport sont routées vers leurs domaines respectifs."""
    # Courses
    res_shop = parser.parse("Ajoute des barres énergétiques pour mon footing à la liste de courses")
    assert res_shop.intent == IntentType.ADD_SHOPPING_ITEM
    assert res_shop.intent != IntentType.LOG_SPORT_SESSION

    # Tâches
    res_task1 = parser.parse("Rappelle-moi de regarder ma séance de sport")
    assert res_task1.intent == IntentType.ADD_TASK
    assert res_task1.intent != IntentType.GET_SPORT_SESSION

    res_task2 = parser.parse("Rappelle-moi de courir demain matin")
    assert res_task2.intent == IntentType.ADD_TASK
    assert res_task2.intent != IntentType.PLAN_SPORT_SESSION


def test_genuine_sport_intents_remain_functional():
    """Vérifie que les intentions purement sportives continuent d'être parfaitement reconnues."""
    # 1. Mise à jour de séance
    res_upd = parser.parse("Sur ma dernière séance j'ai couru 5km avec un rpe à 4 et en 45min 30")
    assert res_upd.intent == IntentType.UPDATE_SPORT_SESSION
    assert res_upd.parameters.get("distance_km") == 5.0
    assert res_upd.parameters.get("ressenti_rpe") == 4

    # 2. Log de course
    res_log = parser.parse("J'ai couru 8 km en 42 minutes")
    assert res_log.intent == IntentType.LOG_SPORT_SESSION
    assert res_log.parameters.get("distance_km") == 8.0

    # 3. Log de renfo
    res_renfo = parser.parse("J'ai fait 30 minutes de renfo, ressenti 7")
    assert res_renfo.intent == IntentType.LOG_SPORT_SESSION
    assert res_renfo.parameters.get("type_seance") == "Renforcement"

    # 4. Consultation de séance
    res_get = parser.parse("Qu'est-ce que j'ai comme séance aujourd'hui ?")
    assert res_get.intent == IntentType.GET_SPORT_SESSION

    # 5. Bilan hebdomadaire
    res_sum = parser.parse("Combien de kilomètres cette semaine ?")
    assert res_sum.intent == IntentType.GET_SPORT_WEEKLY_SUMMARY
