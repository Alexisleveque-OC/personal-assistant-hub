"""Refonte UX (ROADMAP Étape 6) : feuille Repas — logique d'affichage pure (décisions utilisateur du 17/11).

Le module `meals_model.js` (sans import ni DOM) est exécuté sous Node."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
WINDOWS_NODE = Path("/mnt/c/Program Files/nodejs/node.exe")
NODE = shutil.which("node") or (str(WINDOWS_NODE) if WINDOWS_NODE.exists() else None)


def _run(snippet: str):
    if not NODE:
        pytest.skip("Node.js indisponible pour exécuter le module JS")
    source = (STATIC / "js" / "meals_model.js").read_text(encoding="utf-8") + "\n" + snippet
    result = subprocess.run([NODE, "--input-type=module"], input=source, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


# Réponse de GET /api/v1/meals/week (forme réelle de la prod : feuille « Cette semaine », samedi → vendredi)
WEEK = """[
  { day_label: "sam. 14", lunch: null, lunch_ingredients: [], dinner: null, dinner_ingredients: [], is_today: false },
  { day_label: "dim. 15", lunch: "Wrap de légumes", lunch_ingredients: ["Tortilla", "Poivron"], dinner: "Soupe butternut",
    dinner_ingredients: ["Butternut"], is_today: false },
  { day_label: "lun. 16", lunch: null, lunch_ingredients: [], dinner: "Quiche", dinner_ingredients: ["Lardons"], is_today: false },
  { day_label: "mar. 17", lunch: null, lunch_ingredients: [], dinner: "Carotte Bolognaise",
    dinner_ingredients: ["Carottes", "Tomates", "Oignon"], is_today: true },
  { day_label: "mer. 18", lunch: null, lunch_ingredients: [], dinner: null, dinner_ingredients: [], is_today: false },
  { day_label: "jeu. 19", lunch: "Salade", lunch_ingredients: ["oignon", "Feta"], dinner: "Couscous",
    dinner_ingredients: ["Semoule", "Carotte", "Pois chiches"], is_today: false },
  { day_label: "ven. 20", lunch: null, lunch_ingredients: [], dinner: "reste", dinner_ingredients: [], is_today: false }
]"""


def test_strip_lists_the_seven_days_with_past_today_and_future_states():
    out = _run(f"console.log(JSON.stringify(weekStrip({WEEK})));")
    assert [(d["short"], d["num"], d["state"]) for d in out] == [
        ("Sa", "14", "past"), ("Di", "15", "past"), ("Lu", "16", "past"), ("Ma", "17", "today"),
        ("Me", "18", "future"), ("Je", "19", "future"), ("Ve", "20", "future"),
    ]
    assert out[3]["name"] == "mardi 17"


def test_strip_pads_single_digit_days_and_marks_all_future_without_today():
    out = _run("""console.log(JSON.stringify(weekStrip([
  { day_label: "sam. 7", is_today: false }, { day_label: "dim. 8", is_today: false }])));""")
    assert [(d["num"], d["state"], d["name"]) for d in out] == [("07", "future", "samedi 7"), ("08", "future", "dimanche 8")]


def test_default_selection_is_today_or_the_first_day():
    out = _run(f"console.log(JSON.stringify([defaultDay({WEEK}), defaultDay([{{ day_label: 'sam. 7' }}]), defaultDay([])]));")
    assert out == [3, 0, -1]


def test_cards_show_the_chosen_day_then_the_next_one_with_relative_titles():
    out = _run(f"console.log(JSON.stringify(dayCards({WEEK}, 3)));")
    assert [c["title"] for c in out] == ["Aujourd'hui · mardi 17", "Demain · mercredi 18"]
    today, tomorrow = out
    assert today["empty"] is False
    assert today["slots"] == [
        {"key": "midi", "label": "Midi", "dish": None, "ingredients": []},
        {"key": "soir", "label": "Soir", "dish": "Carotte Bolognaise", "ingredients": ["Carottes", "Tomates", "Oignon"]},
    ]
    assert tomorrow["empty"] is True


def test_cards_titles_for_yesterday_other_days_and_the_last_day_alone():
    out = _run(f"""console.log(JSON.stringify([dayCards({WEEK}, 2).map((c) => c.title), dayCards({WEEK}, 5).map((c) => c.title),
  dayCards({WEEK}, 6).map((c) => c.title), dayCards([], 0)]));""")
    assert out == [
        ["Hier · lundi 16", "Aujourd'hui · mardi 17"],
        ["jeudi 19", "vendredi 20"],
        ["vendredi 20"],
        [],
    ]


def test_add_button_prefills_the_composer_with_the_slot_and_day():
    out = _run(f"console.log(JSON.stringify([slotPrefill({WEEK}, 3, 'midi'), slotPrefill({WEEK}, 4, 'soir')]));")
    assert out == ["Midi mardi 17 : ", "Soir mercredi 18 : "]


def test_idea_prompt_asks_for_proposals_without_writing():
    out = _run(f"console.log(JSON.stringify(ideaPrompt({WEEK}, 4)));")
    assert out == (
        "Propose-moi 2 ou 3 idées de repas pour mercredi 18 (midi et soir), de préférence parmi mes recettes. "
        "N'écris rien dans le planning."
    )


SHOPPING = """{
  current_week_items: [{ name: "Oignons x2", checked: true }, { name: "Lait", checked: false }],
  waiting_list: [{ item: "Feta", is_bought: false }]
}"""


def test_week_ingredients_run_from_today_to_friday_deduplicated_and_flag_the_listed_ones():
    out = _run(f"console.log(JSON.stringify(weekIngredients({WEEK}, {SHOPPING})));")
    assert out == [
        {"name": "Carottes", "listed": False},
        {"name": "Tomates", "listed": False},
        {"name": "Oignon", "listed": True},
        {"name": "Feta", "listed": True},
        {"name": "Semoule", "listed": False},
        {"name": "Pois chiches", "listed": False},
    ]


def test_week_ingredients_start_on_the_first_day_without_today_and_tolerate_no_shopping():
    out = _run("""console.log(JSON.stringify(weekIngredients([
  { day_label: "sam. 7", lunch: "A", lunch_ingredients: ["Riz"], dinner: null, dinner_ingredients: [] }], null)));""")
    assert out == [{"name": "Riz", "listed": False}]


def test_ingredients_message_for_otis():
    out = _run("console.log(JSON.stringify(ingredientsMessage(['Carottes', 'Semoule'])));")
    assert out == "Ajoute aux courses : Carottes, Semoule."
