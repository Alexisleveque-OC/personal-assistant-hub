"""Refonte UX (ROADMAP Étape 1) : accueil — « Dernières actions », 4 bulles, feuille Conversation.

La logique des bulles (home_model.js, sans import) est exécutée sous Node."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
WINDOWS_NODE = Path("/mnt/c/Program Files/nodejs/node.exe")
NODE = shutil.which("node") or (str(WINDOWS_NODE) if WINDOWS_NODE.exists() else None)
client = TestClient(app)


def _run(snippet: str):
    if not NODE:
        pytest.skip("Node.js indisponible pour exécuter le module JS")
    source = (STATIC / "js" / "home_model.js").read_text(encoding="utf-8") + "\n" + snippet
    result = subprocess.run([NODE, "--input-type=module"], input=source, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


# ---------- 🛒 À acheter ----------

def test_shopping_bubble_counts_this_week_items_left_and_lists_the_first_three():
    out = _run("""
const data = { current_week_items: [
  { name: "Banane", checked: false }, { name: "Pomme", checked: true }, { name: "Avocat x4", checked: false },
  { name: "Lait", checked: false }, { name: "Riz", checked: false } ],
  waiting_list: [{ item: "Lessive" }] };
console.log(JSON.stringify([shoppingSummary(data, ["Lait"]), shoppingSummary({ current_week_items: [] }, []),
  shoppingSummary({ current_week_items: [{ name: "Pain", checked: false }] }, [])]));
""")
    assert out == [
        {"count": 3, "value": "3 articles", "foot": "Banane, Avocat x4, Riz"},
        {"count": 0, "value": "Rien à acheter", "foot": ""},
        {"count": 1, "value": "1 article", "foot": "Pain"},
    ]


def test_shopping_bubble_ends_with_an_ellipsis_when_more_than_three_items_are_left():
    out = _run("""
const data = { current_week_items: ["A", "B", "C", "D"].map((name) => ({ name, checked: false })) };
console.log(JSON.stringify(shoppingSummary(data, [])));
""")
    assert out == {"count": 4, "value": "4 articles", "foot": "A, B, C…"}


# ---------- 📌 Prochaine tâche ----------

def test_next_task_is_the_earliest_dated_one_otherwise_the_first_without_date():
    out = _run("""
const taches = [
  { titre: "Sans date", echeance: null }, { titre: "Permixon", echeance: "2026-11-12" },
  { titre: "En retard", echeance: "2026-11-08" }, { titre: "Plus tard", echeance: "2026-11-20" } ];
console.log(JSON.stringify([nextTask(taches), nextTask([{ titre: "Seule", echeance: null }]), nextTask([])]));
""")
    assert out == [
        {"value": "En retard", "foot": "Dim. 8 nov."},
        {"value": "Seule", "foot": "Sans date"},
        {"value": "Aucune tâche", "foot": ""},
    ]


# ---------- 🍲 Ce soir ----------

def test_tonight_bubble_shows_dinner_and_lunch_of_today():
    out = _run("""
const week = [ { is_today: false, lunch: "X", dinner: "Y" }, { is_today: true, lunch: null, dinner: "Soupe vermicelle" } ];
console.log(JSON.stringify([tonightMeal(week), tonightMeal([{ is_today: true, lunch: "Quiche", dinner: "" }]), tonightMeal([])]));
""")
    assert out == [
        {"value": "Soupe vermicelle", "foot": "Midi : rien de prévu"},
        {"value": "Rien de prévu", "foot": "Midi : Quiche"},
        {"value": "Rien de prévu", "foot": "Midi : rien de prévu"},
    ]


# ---------- 🏃 Sport du jour ----------

def test_sport_bubble_shows_today_session_otherwise_rest_and_the_coach_message():
    out = _run("""
console.log(JSON.stringify([
  sportOfTheDay({ seances: [{ type_seance: "Sortie longue", distance_km: 12 }], coach_tip: { message: "Semaine de décharge." } }),
  sportOfTheDay({ seances: [{ type_seance: "Renforcement", distance_km: null }], coach_tip: null }),
  sportOfTheDay({ seances: [], coach_tip: { message: "Repos bien mérité." } }),
]));
""")
    assert out == [
        {"value": "Sortie longue · 12 km", "foot": "Semaine de décharge."},
        {"value": "Renforcement", "foot": ""},
        {"value": "Repos 😌", "foot": "Repos bien mérité."},
    ]


# ---------- Dernières actions ----------

def test_action_time_is_the_hour_today_then_yesterday_then_the_day():
    out = _run("""
const now = new Date(2026, 10, 10, 19, 0);
const local = (d, h, m) => new Date(2026, 10, d, h, m).toISOString();
console.log(JSON.stringify([actionTime(local(10, 18, 36), now), actionTime(local(9, 21, 0), now), actionTime(local(5, 8, 0), now), actionTime(null, now)]));
""")
    assert out == ["18:36", "hier", "jeu. 5", ""]


def test_last_otis_reply_is_read_from_the_saved_conversation():
    out = _run("""
console.log(JSON.stringify([
  lastAssistantReply([{ role: "user", text: "Salut" }, { role: "assistant", text: "Bonjour !" }, { role: "user", text: "Et ?" }]),
  lastAssistantReply([]),
]));
""")
    assert out == ["Bonjour !", None]


# ---------- Page servie ----------

def _rendered_html() -> str:
    return re.sub(r"<!--.*?-->", "", client.get("/app").text, flags=re.DOTALL)


def test_home_has_the_activity_block_and_four_bubbles_opening_their_section():
    html = _rendered_html()
    main = html[html.index('<main class="app__main"'):html.index("</main>")]

    assert '<section class="activity" id="home-activity" aria-label="Dernières actions">' in main
    for section, label in (("repas", "🍲 Ce soir"), ("sport", "🏃 Sport du jour"),
                           ("courses", "🛒 À acheter"), ("taches", "📌 Prochaine tâche")):
        assert re.search(rf'<a href="#" class="bubble" data-section="{section}"[^>]*>\s*<span class="bubble__label">{label}</span>', main), section
    assert 'id="chat-stream"' not in main


def test_conversation_sheet_holds_the_chat_the_suggestions_and_a_new_thread_button():
    html = _rendered_html()
    match = re.search(r'<section class="sheet" id="view-conversation"([^>]*)>(.*?)\n    </section>', html, re.S)

    assert match
    attrs, body = match.groups()
    assert 'role="dialog"' in attrs and 'aria-modal="true"' in attrs
    for element in ('id="chat-stream"', 'id="chips-container"', 'id="btn-new-chat"', '<div class="composer-slot"></div>'):
        assert element in body


def test_hands_free_otis_is_a_switch_in_the_menu_with_its_live_status():
    html = _rendered_html()
    drawer = html[html.index('<nav class="drawer"'):html.index("</nav>", html.index('<nav class="drawer"'))]

    assert 'id="wake-word-switch"' in drawer
    assert 'id="wake-word-indicator"' in drawer


def test_home_modules_are_precached():
    sw = client.get("/sw.js").text
    for path in ("/static/js/home_model.js", "/static/js/views/home_view.js"):
        assert client.get(path).status_code == 200
        assert f'"{path}"' in sw
