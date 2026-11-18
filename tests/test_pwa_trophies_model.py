"""Refonte UX (ROADMAP Étape 3) : écran Trophées — logique d'affichage pure.

Le module `trophies_model.js` (sans import ni DOM) est exécuté sous Node."""

from tests.js_helpers import js_source, run_node



def _run(snippet: str):
    return run_node(js_source("trophies_model.js") + "\n" + snippet)


BADGES = """[
  { id: "a", title: "Premier Dix Bornes", description: "Boucler 10 km d'une seule traite", icon: "🥉", category: "mono_session",
    is_unlocked: true, is_secret: false, unlocked_at: "2026-10-04", current_value: 10.3, target_value: 10, unit: "km", progress_pct: 100, rarity: "bronze" },
  { id: "b", title: "L'Explorateur des 15", description: "Dépasser 15 km", icon: "🥈", category: "mono_session",
    is_unlocked: false, is_secret: false, unlocked_at: null, current_value: 10.29, target_value: 15, unit: "km", progress_pct: 68, rarity: "bronze" },
  { id: "c", title: "Le Cap des 75 min", description: "1h15", icon: "⏱️", category: "mono_session",
    is_unlocked: false, is_secret: false, unlocked_at: null, current_value: 1.1, target_value: 1.25, unit: "h", progress_pct: 90, rarity: "bronze" },
  { id: "d", title: "L'Épreuve d'Athènes", description: "42 km", icon: "👑", category: "mono_session",
    is_unlocked: false, is_secret: false, unlocked_at: null, current_value: 10.3, target_value: 42.2, unit: "km", progress_pct: 24, rarity: "diamant" },
  { id: "e", title: "L'Heure Pleine (1h)", description: "1h sans s'arrêter", icon: "⏱️", category: "mono_session",
    is_unlocked: true, is_secret: false, unlocked_at: "2026-11-12", current_value: 1, target_value: 1, unit: "h", progress_pct: 100, rarity: "bronze" },
  { id: "f", title: "Centurion (100 km)", description: "100 km", icon: "🥉", category: "distance",
    is_unlocked: false, is_secret: false, unlocked_at: null, current_value: 84.24, target_value: 100, unit: "km", progress_pct: 84, rarity: "argent" },
  { id: "g", title: "Badge Secret 🥧", description: "Une énigme…", icon: "🔒", category: "secret",
    is_unlocked: false, is_secret: true, unlocked_at: null, current_value: 0, target_value: 1, unit: null, progress_pct: 0, rarity: "or" },
  { id: "h", title: "Vous Ne Passerez Pas !", description: "Barrer la route au dénivelé", icon: "🧙", category: "pop_culture",
    is_unlocked: false, is_secret: false, unlocked_at: null, current_value: 0, target_value: null, unit: null, progress_pct: 0, rarity: "argent" },
  { id: "i", title: "Objectif Lune", description: "384 400 km", icon: "🌕", category: "absurde",
    is_unlocked: false, is_secret: false, unlocked_at: null, current_value: 84.24, target_value: 384400, unit: "km", progress_pct: 0, rarity: "mythique" },
  { id: "j", title: "Kilomètre Vertical", description: "1 000 m", icon: "⛰️", category: "denivele",
    is_unlocked: false, is_secret: false, unlocked_at: null, current_value: 517, target_value: 1000, unit: "m", progress_pct: 51, rarity: "argent" }
]"""


def test_tabs_follow_the_user_grouping():
    out = _run("console.log(JSON.stringify(TROPHY_TABS.map((t) => [t.key, t.label, t.categories])));")
    assert out == [
        ["seance", "⚡ En une séance", ["mono_session"]],
        ["cumuls", "📈 Cumuls", ["distance", "denivele", "temps", "regularite"]],
        ["pop", "🧙 Pop‑culture", ["pop_culture"]],
        ["secrets", "🕵️ Secrets & absurdes", ["secret", "absurde"]],
    ]


def test_tab_lists_unlocked_first_then_by_progress_and_puts_legendary_tiers_aside():
    out = _run(f"""
const t = trophiesForTab({BADGES}, "seance", "2026-11-16");
const c = trophiesForTab({BADGES}, "cumuls", "2026-11-16");
const s = trophiesForTab({BADGES}, "secrets", "2026-11-16");
console.log(JSON.stringify([t.main.map((x) => x.id), t.legendary.map((x) => x.id), c.main.map((x) => x.id),
  s.main.map((x) => x.id), s.legendary.map((x) => x.id)]));
""")
    assert out == [["e", "a", "c", "b"], ["d"], ["f", "j"], ["g"], ["i"]]


def test_unlocked_card_shows_description_tier_and_date_and_pops_for_seven_days():
    out = _run(f"""
const cards = trophiesForTab({BADGES}, "seance", "2026-11-16").main;
console.log(JSON.stringify([cards[0], cards[1].justUnlocked, isJustUnlocked("2026-11-09", "2026-11-16"),
  isJustUnlocked("2026-11-08", "2026-11-16"), isJustUnlocked(null, "2026-11-16")]));
""")
    assert out == [
        {"id": "e", "emoji": "⏱️", "name": "L'Heure Pleine (1h)", "tier": "bronze", "tierLabel": "BRONZE",
         "unlocked": True, "justUnlocked": True, "desc": "1h sans s'arrêter", "doneLabel": "Débloqué ✓ · 12 nov.",
         "progressPct": None, "progressLabel": None},
        False, True, False, False,
    ]


def test_locked_card_shows_progress_with_values_or_encouragement_from_ninety_percent():
    out = _run(f"""
const cards = trophiesForTab({BADGES}, "seance", "2026-11-16").main;
const c = trophiesForTab({BADGES}, "cumuls", "2026-11-16").main;
console.log(JSON.stringify([cards[2], cards[3].progressLabel, c[1].progressLabel,
  trophiesForTab({BADGES}, "secrets", "2026-11-16").legendary[0].progressLabel]));
""")
    assert out == [
        {"id": "c", "emoji": "⏱️", "name": "Le Cap des 75 min", "tier": "bronze", "tierLabel": "BRONZE",
         "unlocked": False, "justUnlocked": False, "desc": None, "doneLabel": None,
         "progressPct": 90, "progressLabel": "90 % · encore un effort !"},
        "10,3 / 15 km · 68 %", "517 / 1 000 m · 51 %", "84,2 / 384 400 km · 0 %",
    ]


def test_secret_and_untargeted_locked_cards_show_their_hint_without_progress():
    out = _run(f"""
const secret = trophiesForTab({BADGES}, "secrets", "2026-11-16").main[0];
const pop = trophiesForTab({BADGES}, "pop", "2026-11-16").main[0];
console.log(JSON.stringify([[secret.desc, secret.progressPct, secret.tierLabel], [pop.desc, pop.progressPct, pop.tierLabel]]));
""")
    assert out == [["Une énigme…", None, "OR"], ["Barrer la route au dénivelé", None, "ARGENT"]]


def test_overview_and_imminent_milestone_with_the_badge_progress():
    out = _run(f"""
console.log(JSON.stringify([
  trophyOverview({{ unlocked_count: 13, total_badges: 83 }}),
  trophyOverview({{ unlocked_count: 0, total_badges: 0 }}),
  imminentMilestone({{ badges: {BADGES}, imminent_milestones: [{{ badge_id: "f", message: "Plus que 15.8 km !" }}] }}),
  imminentMilestone({{ badges: [], imminent_milestones: [] }}),
]));
""")
    assert out == [
        {"unlocked": 13, "total": 83, "pct": 16},
        {"unlocked": 0, "total": 0, "pct": 0},
        {"message": "Plus que 15.8 km !", "pct": 84},
        None,
    ]


def test_exploits_records_and_equivalences_follow_the_mockup():
    out = _run("""
console.log(JSON.stringify([
  exploits(["🔥 OMG ! Tu as couru 21 marathons !", "⛰️ Plus de 5 000 m gravis", "Sans émoji"]),
  [
    { record_type: "longest_run", title: "Plus Longue Sortie", value: 10.29, formatted_value: "10.29 km", date: "2026-10-04" },
    { record_type: "max_elevation", title: "Plus Gros Dénivelé (D+)", value: 68, formatted_value: "68 m D+", date: "2026-10-04" },
    { record_type: "best_pace", title: "Allure Record (≥3 km)", value: 333, formatted_value: "05:33 /km", date: "2026-09-30" },
    { record_type: "autre", title: "Record X", value: 1, formatted_value: "1 x", date: null },
  ].map(recordTile),
  [
    { icon: "🗼", title: "Ascension Verticale", text: "phrase", headline: "1,7 × la tour Eiffel", detail: "517 m de D+ cumulés" },
    { icon: "🚀", title: "Objectif Alunissage", text: "Plus que 384 315 km", headline: null, detail: null },
  ].map(equivalence),
]));
""")
    assert out == [
        [{"emoji": "🔥", "text": "OMG ! Tu as couru 21 marathons !"}, {"emoji": "⛰️", "text": "Plus de 5 000 m gravis"},
         {"emoji": "🏅", "text": "Sans émoji"}],
        [
            {"emoji": "📏", "value": "10,29 km", "label": "plus longue · 4 oct."},
            {"emoji": "🏔️", "value": "68 m", "label": "plus gros D+ · 4 oct."},
            {"emoji": "🚀", "value": "5:33", "label": "allure ≥3 km · 30 sept."},
            {"emoji": "🏅", "value": "1 x", "label": "Record X"},
        ],
        [{"emoji": "🗼", "headline": "1,7 × la tour Eiffel", "detail": "517 m de D+ cumulés"},
         {"emoji": "🚀", "headline": "Objectif Alunissage", "detail": "Plus que 384 315 km"}],
    ]
