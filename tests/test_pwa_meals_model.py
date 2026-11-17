"""Refonte UX (ROADMAP Étape 6) : feuille Repas — logique d'affichage pure (décisions utilisateur du 17/11).

Retours du test téléphone (17/11) : lecture de l'onglet annuel par dates, navigation ‹ › de semaine en semaine,
les 7 jours en liste, ingrédients de la semaine affichée (bouton masqué pour une semaine passée).
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


TODAY = '"2026-11-17"'

# `week_plan` de GET /api/v1/meals/week (onglet annuel, samedi → vendredi)
WEEK = """[
  { date: "2026-11-14", day_label: "sam. 14", lunch: null, lunch_ingredients: [], dinner: null, dinner_ingredients: [] },
  { date: "2026-11-15", day_label: "dim. 15", lunch: "Wrap de légumes", lunch_ingredients: ["Tortilla", "Poivron"],
    dinner: "Soupe butternut", dinner_ingredients: ["Butternut"] },
  { date: "2026-11-16", day_label: "lun. 16", lunch: null, lunch_ingredients: [], dinner: "Quiche", dinner_ingredients: ["Lardons"] },
  { date: "2026-11-17", day_label: "mar. 17", lunch: null, lunch_ingredients: [], dinner: "Carotte Bolognaise",
    dinner_ingredients: ["Carottes", "Tomates", "Oignon"], is_today: true },
  { date: "2026-11-18", day_label: "mer. 18", lunch: null, lunch_ingredients: [], dinner: null, dinner_ingredients: [] },
  { date: "2026-11-19", day_label: "jeu. 19", lunch: "Salade", lunch_ingredients: ["oignon", "Feta"], dinner: "Couscous",
    dinner_ingredients: ["Semoule", "Carotte", "Pois chiches"] },
  { date: "2026-11-20", day_label: "ven. 20", lunch: null, lunch_ingredients: [], dinner: "reste", dinner_ingredients: [] }
]"""


def test_strip_lists_the_seven_days_with_past_today_and_future_states():
    out = _run(f"console.log(JSON.stringify(weekStrip({WEEK}, {TODAY})));")
    assert [(d["short"], d["num"], d["state"]) for d in out] == [
        ("Sa", "14", "past"), ("Di", "15", "past"), ("Lu", "16", "past"), ("Ma", "17", "today"),
        ("Me", "18", "future"), ("Je", "19", "future"), ("Ve", "20", "future"),
    ]
    assert out[3]["name"] == "mardi 17"


def test_strip_states_of_other_weeks_follow_their_dates():
    out = _run("""console.log(JSON.stringify([
  weekStrip([{ date: "2026-11-07", day_label: "sam. 7" }], "2026-11-17").map((d) => [d.num, d.state, d.name]),
  weekStrip([{ date: "2026-11-21", day_label: "sam. 21" }], "2026-11-17").map((d) => d.state)]));""")
    assert out == [[["07", "past", "samedi 7"]], ["future"]]


def test_default_selection_is_today_or_the_first_day():
    out = _run(f"""console.log(JSON.stringify([defaultDay({WEEK}, {TODAY}), defaultDay({WEEK}, "2026-12-01"),
  defaultDay([], {TODAY})]));""")
    assert out == [3, 0, -1]


def test_cards_cover_the_whole_week_with_relative_titles():
    out = _run(f"console.log(JSON.stringify(dayCards({WEEK}, {TODAY})));")
    assert [c["title"] for c in out] == [
        "samedi 14", "dimanche 15", "Hier · lundi 16", "Aujourd'hui · mardi 17", "Demain · mercredi 18", "jeudi 19",
        "vendredi 20",
    ]
    today = out[3]
    assert today["index"] == 3 and today["empty"] is False
    assert today["slots"] == [
        {"key": "midi", "label": "Midi", "dish": None, "ingredients": []},
        {"key": "soir", "label": "Soir", "dish": "Carotte Bolognaise", "ingredients": ["Carottes", "Tomates", "Oignon"]},
    ]
    assert out[4]["empty"] is True
    assert _run(f"console.log(JSON.stringify(dayCards([], {TODAY})));") == []


def test_add_button_prefills_the_composer_with_the_slot_and_full_date():
    out = _run(f"console.log(JSON.stringify([slotPrefill({WEEK}, 3, 'midi'), slotPrefill({WEEK}, 4, 'soir')]));")
    assert out == ["Midi mardi 17 novembre : ", "Soir mercredi 18 novembre : "]


def test_idea_prompt_asks_for_proposals_without_writing():
    out = _run(f"console.log(JSON.stringify(ideaPrompt({WEEK}, 4)));")
    assert out == (
        "Propose-moi 2 ou 3 idées de repas pour mercredi 18 novembre (midi et soir), de préférence parmi mes recettes. "
        "N'écris rien dans le planning."
    )


def test_week_navigation_titles_and_date_ranges():
    out = _run("""console.log(JSON.stringify([
  weekNav(0, "2026-11-14", "2026-11-20"), weekNav(1, "2026-11-21", "2026-11-27"), weekNav(-1, "2026-11-07", "2026-11-13"),
  weekNav(3, "2026-11-28", "2026-12-04"), weekNav(-2, "2026-12-26", "2027-01-01")]));""")
    assert out == [
        {"title": "Cette semaine", "range": "14 – 20 nov."},
        {"title": "Semaine prochaine", "range": "21 – 27 nov."},
        {"title": "Semaine dernière", "range": "7 – 13 nov."},
        {"title": "Dans 3 semaines", "range": "28 nov. – 4 déc."},
        {"title": "Il y a 2 semaines", "range": "26 déc. – 1 janv."},
    ]


SHOPPING = """{
  current_week_items: [{ name: "Oignons x2", checked: true }, { name: "Lait", checked: false }],
  waiting_list: [{ item: "Feta", is_bought: false }]
}"""


def test_week_ingredients_run_from_today_deduplicated_and_flag_the_listed_ones():
    out = _run(f"console.log(JSON.stringify(weekIngredients({WEEK}, {SHOPPING}, {TODAY})));")
    assert out == [
        {"name": "Carottes", "listed": False},
        {"name": "Tomates", "listed": False},
        {"name": "Oignon", "listed": True},
        {"name": "Feta", "listed": True},
        {"name": "Semoule", "listed": False},
        {"name": "Pois chiches", "listed": False},
    ]


def test_a_future_week_gives_all_its_ingredients_and_a_past_week_none():
    out = _run(f"""console.log(JSON.stringify([
  weekIngredients({WEEK}, null, "2026-11-01").map((i) => i.name).slice(0, 3),
  hasIngredientsButton({WEEK}, "2026-11-01"), hasIngredientsButton({WEEK}, "2026-11-20"),
  hasIngredientsButton({WEEK}, "2026-11-21"), hasIngredientsButton([], {TODAY})]));""")
    assert out == [["Tortilla", "Poivron", "Butternut"], True, True, False, False]


def test_ingredients_message_for_otis():
    out = _run("console.log(JSON.stringify(ingredientsMessage(['Carottes', 'Semoule'])));")
    assert out == "Ajoute aux courses : Carottes, Semoule."


def test_add_on_button_prefills_a_request_to_complete_the_dish():
    """Retours du 17/11 : « + Ajouter un plat » sur un créneau rempli → Otis complète (« Quiche lorraine + Coleslaw »)."""
    out = _run(f"console.log(JSON.stringify([addOnPrefill({WEEK}, 3, 'soir'), addOnPrefill({WEEK}, 5, 'midi')]));")
    assert out == ["Ajouter au soir de mardi 17 novembre : ", "Ajouter au midi de jeudi 19 novembre : "]
