"""Refonte UX (ROADMAP Étape 5) : feuille Tâches — logique d'affichage pure.

Le module `tasks_model.js` (sans import ni DOM) est exécuté sous Node."""
import json

from tests.js_helpers import js_source, run_node

TODAY = "2026-11-16"  # lundi : la semaine court jusqu'au dimanche 22


def _run(snippet: str):
    return run_node(js_source("tasks_model.js") + "\n" + snippet)


def task(id, titre, echeance=None, heure=None, parent=None, notes=None, en_retard=False):
    return {"id": id, "titre": titre, "echeance": echeance, "heure": heure, "parent": parent, "notes": notes,
            "en_retard": en_retard}


def sheet(tasks):
    return _run(f"console.log(JSON.stringify(taskSheet({json.dumps(tasks)}, '{TODAY}')));")


def test_sections_by_due_date_in_order_and_empty_ones_omitted():
    out = sheet([
        task("a", "Sans date"),
        task("b", "Plus tard", "2026-12-03"),
        task("c", "Retard", "2026-11-09", en_retard=True),
        task("d", "Dimanche", "2026-11-22"),
        task("e", "Aujourd'hui", "2026-11-16"),
    ])
    assert [(s["key"], s["title"], [i["titre"] for i in s["items"]]) for s in out["sections"]] == [
        ("late", "En retard", ["Retard"]),
        ("week", "Cette semaine", ["Aujourd'hui", "Dimanche"]),
        ("later", "Plus tard", ["Plus tard"]),
        ("none", "Sans date", ["Sans date"]),
    ]
    assert out["groups"] == []
    assert out["count"] == 5


def test_badges_show_weekday_this_week_day_and_month_otherwise_and_the_hour():
    out = sheet([
        task("c", "Retard", "2026-11-09"),
        task("d", "ORL", "2026-11-19", heure="14:30"),
        task("b", "Plus tard", "2026-12-03"),
        task("a", "Sans date"),
    ])
    badges = {i["titre"]: i["badge"] for s in out["sections"] for i in s["items"]}
    assert badges == {
        "Retard": {"text": "9 nov.", "tone": "danger"},
        "ORL": {"text": "jeu. 19 · 14:30", "tone": "accent"},
        "Plus tard": {"text": "3 déc.", "tone": "muted"},
        "Sans date": None,
    }


def test_same_day_tasks_are_ordered_by_hour_untimed_first():
    out = sheet([
        task("a", "Soir", "2026-11-18", heure="19:00"),
        task("b", "Journée", "2026-11-18"),
        task("c", "Matin", "2026-11-18", heure="08:15"),
    ])
    assert [i["titre"] for i in out["sections"][0]["items"]] == ["Journée", "Matin", "Soir"]


def test_parent_with_open_subtasks_becomes_a_group_not_a_row():
    out = sheet([
        task("p", "Rendez-vous à prendre"),
        task("c1", "ORL", parent="p"),
        task("c2", "Radio", "2026-11-20", parent="p"),
        task("x", "Envoyer les documents"),
    ])
    assert [(s["key"], [i["titre"] for i in s["items"]]) for s in out["sections"]] == [("none", ["Envoyer les documents"])]
    group = out["groups"][0]
    assert (group["id"], group["title"], [i["titre"] for i in group["items"]]) == ("p", "Rendez-vous à prendre", ["ORL", "Radio"])
    assert group["items"][1]["badge"] == {"text": "ven. 20", "tone": "accent"}
    assert out["count"] == 3


def test_subtask_whose_parent_is_not_open_is_a_normal_task():
    out = sheet([task("c1", "ORL", parent="absent")])
    assert out["sections"][0]["items"][0]["titre"] == "ORL"


def test_link_is_the_first_url_of_the_notes_then_of_the_title():
    out = _run("""console.log(JSON.stringify([
      firstUrl({ titre: "Ronde", notes: "Inscription : https://example.org/ronde?x=1. Merci" }),
      firstUrl({ titre: "Voir http://a.fr/b", notes: null }),
      firstUrl({ titre: "Rien", notes: "pas de lien, javascript:alert(1)" }),
      firstUrl({ titre: "(https://c.fr/d)", notes: "" }),
    ]));""")
    assert out == ["https://example.org/ronde?x=1", "http://a.fr/b", None, "https://c.fr/d"]


def test_rows_carry_id_link_hour_and_reminder():
    out = sheet([{**task("a", "Ronde", notes="https://e.org"), "rappel_minutes_avant": None}])
    assert out["sections"][0]["items"][0] == {
        "id": "a", "titre": "Ronde", "badge": None, "link": "https://e.org", "heure": None, "rappel_minutes_avant": None,
    }


def test_due_chip_and_message_suffix_for_otis():
    out = _run("""console.log(JSON.stringify([
      dueChipLabel({ date: "2026-11-19", time: "" }),
      dueChipLabel({ date: "2026-11-19", time: "14:30" }),
      withDue("ORL", { date: "2026-11-19", time: "" }),
      withDue("ORL", { date: "2026-11-19", time: "14:30" }),
      withDue("ORL", null),
    ]));""")
    assert out == [
        "jeu. 19 nov.",
        "jeu. 19 nov. · 14:30",
        "ORL — échéance le jeudi 19 novembre 2026",
        "ORL — échéance le jeudi 19 novembre 2026 à 14:30",
        "ORL",
    ]


def test_open_rows_drop_group_parents_for_the_home_bubble_and_counter():
    out = _run("""console.log(JSON.stringify(openRows([
      { id: "p", titre: "Rendez-vous" }, { id: "c", titre: "ORL", parent: "p" }, { id: "x", titre: "Seule" },
    ]).map((t) => t.titre)));""")
    assert out == ["ORL", "Seule"]
