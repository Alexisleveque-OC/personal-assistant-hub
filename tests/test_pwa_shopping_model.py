"""Refonte UX (ROADMAP Étape 4) : feuille Courses — logique d'affichage pure.

Le module `shopping_model.js` (sans import ni DOM) est exécuté sous Node."""

from tests.js_helpers import js_source, run_node



def _run(snippet: str):
    return run_node(js_source("shopping_model.js") + "\n" + snippet)


# Réponse de GET /api/v1/meals/shopping (forme réelle de la prod)
DATA = """{
  current_week_items: [
    { name: "Lardon x2", checked: false, rayon: "Charcuterie", destination_sheet: "Cette semaine" },
    { name: "pomme", checked: true, rayon: "Fruits", destination_sheet: "Cette semaine" },
    { name: "Banane", checked: false, rayon: "Fruits", destination_sheet: "Cette semaine" },
    { name: "endive x3", checked: false, rayon: "Légumes", destination_sheet: "Cette semaine" },
    { name: "Ficelle", checked: false, rayon: null, destination_sheet: "Cette semaine" },
    { name: "Glaçons", checked: false, rayon: "Rayon inconnu", destination_sheet: "Cette semaine" }
  ],
  waiting_list: [
    { item: "Dentifrice", is_bought: false, added_at: "10/11/2026", rayon: "Hygiène" },
    { item: "Piles", is_bought: false, added_at: null, rayon: null }
  ],
  rayons_order: { "Fruits": 1, "Légumes": 2, "Charcuterie": 5, "Hygiène": 14 }
}"""


def test_quantity_suffix_becomes_a_badge_and_the_name_is_kept():
    out = _run("""console.log(JSON.stringify(["endive x3", "Lardon X2", "Mozza ×2", "Pois chiches", "x2", "Boxer", "Eau x 6"]
      .map(splitQuantity)));""")
    assert out == [
        {"label": "endive", "qty": "x3"},
        {"label": "Lardon", "qty": "x2"},
        {"label": "Mozza", "qty": "x2"},
        {"label": "Pois chiches", "qty": None},
        {"label": "x2", "qty": None},
        {"label": "Boxer", "qty": None},
        {"label": "Eau", "qty": "x6"},
    ]


def test_lists_merge_sheet_checks_with_checks_made_on_this_phone():
    out = _run(f"console.log(JSON.stringify(shoppingLists({DATA}, ['Banane'])));")
    week = {i["name"]: i["checked"] for i in out["week"]}
    assert week == {"Lardon x2": False, "pomme": True, "Banane": True, "endive x3": False, "Ficelle": False, "Glaçons": False}
    assert out["waiting"] == [
        {"name": "Dentifrice", "rayon": "Hygiène", "checked": False},
        {"name": "Piles", "rayon": None, "checked": False},
    ]


def test_lists_tolerate_an_empty_or_missing_payload():
    out = _run("console.log(JSON.stringify([shoppingLists(null), shoppingLists({})]));")
    assert out == [{"week": [], "waiting": []}, {"week": [], "waiting": []}]


def test_groups_follow_the_store_order_with_unknown_aisles_before_misc():
    out = _run(f"""const lists = shoppingLists({DATA}, []);
console.log(JSON.stringify(groupByRayon(lists.week, {DATA}.rayons_order)));""")
    assert [g["rayon"] for g in out] == ["Fruits", "Légumes", "Charcuterie", "Rayon inconnu", "Divers"]
    fruits = out[0]
    assert fruits["count"] == 2
    assert fruits["items"] == [
        {"name": "pomme", "label": "pomme", "qty": None, "checked": True},
        {"name": "Banane", "label": "Banane", "qty": None, "checked": False},
    ]
    assert out[2]["items"][0] == {"name": "Lardon x2", "label": "Lardon", "qty": "x2", "checked": False}


def test_store_order_falls_back_to_the_default_aisles_and_ignores_accents():
    out = _run("""const items = [
  { name: "Surgelés", rayon: "Surgelé", checked: false },
  { name: "Steak", rayon: "viande", checked: false },
  { name: "Salade", rayon: "legumes", checked: false }];
console.log(JSON.stringify(groupByRayon(items, null).map((g) => g.rayon)));""")
    assert out == ["legumes", "viande", "Surgelé"]


def test_remaining_items_are_the_unchecked_ones():
    out = _run(f"""const lists = shoppingLists({DATA}, ['Banane']);
console.log(JSON.stringify([remainingCount(lists.week), remainingNames(lists.week), remainingCount(lists.waiting), remainingCount([])]));""")
    assert out == [4, ["Lardon x2", "endive x3", "Ficelle", "Glaçons"], 2, 0]


def test_phone_checks_are_added_once_and_removed_on_uncheck():
    out = _run("""console.log(JSON.stringify([
  toggleStoredCheck(["a"], "b", true), toggleStoredCheck(["a", "b"], "b", true),
  toggleStoredCheck(["a", "b"], "a", false), toggleStoredCheck([], "a", false)]));""")
    assert out == [["a", "b"], ["a", "b"], ["b"], []]


def test_completion_message_congratulates_or_lists_what_is_left():
    out = _run("""console.log(JSON.stringify([
  completionMessage([], true), completionMessage(["Lait", "Oeufs", "Pain", "Beurre", "Sel"], false)]));""")
    done, left = out
    assert done["tone"] == "success"
    assert done["title"] == "🎉 Félicitations !"
    assert done["text"] == "Vous avez tout pris dans votre liste. Vos courses sont complètes !"
    assert done["items"] == []
    assert done["synced"] is True
    assert done["speech"] == "Félicitations, vous avez tout pris ! Vos courses sont complètes et enregistrées dans le Google Sheet."
    assert left["tone"] == "warn"
    assert left["title"] == "⚠️ Il vous reste encore 5 articles à prendre"
    assert left["items"] == ["Lait", "Oeufs", "Pain", "Beurre", "Sel"]
    assert left["synced"] is False
    assert left["speech"] == "Attention, il vous reste encore 5 article(s) à prendre : Lait, Oeufs, Pain, Beurre."


def test_completion_message_uses_singular_for_one_item():
    out = _run("console.log(JSON.stringify(completionMessage(['Lait'], true).title));")
    assert out == "⚠️ Il vous reste encore 1 article à prendre"
