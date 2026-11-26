"""Phase 10, étape 7a : écran Budget — logique d'affichage pure (`budget_model.js`, sans import ni DOM, sous Node).

Cadrage du 25/11 : graphique Dépenses vs Revenus par mois + épargné du mois actif ; groupes de `Gestion` repliables
avec leur total ; par catégorie, reste total (rouge si négatif) et « ce mois : dépensé X / budget Y » avec barre.
Le serveur n'envoie pas le groupe Revenus (décision utilisateur du 26/11) : les revenus ne sont que dans le graphique.
"""
import json

from tests.js_helpers import js_source, run_node

NBSP, NNBSP = " ", " "


def _run(snippet: str):
    return run_node(js_source("budget_model.js") + "\n" + snippet)


def month(m, expenses, income):
    return {"month": {"year": 2026, "month": m}, "expenses": expenses, "income": income}


def cat(name, remaining, spent, budget):
    return {"name": name, "total_remaining": remaining, "month_spent": spent, "month_budget": budget}


OVERVIEW = {
    "active_month": {"year": 2026, "month": 11},
    "saved": 2012.35,
    "series": [month(9, 4458.4, 4346.92), month(10, 4839.65, 4468.81), month(11, 203.2, 2215.55)],
    "groups": [
        {"name": "Courants", "total_remaining": 404.91, "categories": [
            cat("Course", 923.15, 76.02, 1000), cat("Restaurant", -100.69, 49, 35), cat("Voiture", 0, 0, 0),
            cat("Imprévu", 10, 12.5, 0),
        ]},
        {"name": "Loisir", "total_remaining": 120, "categories": [cat("Sorties", 120, 0, 50)]},
    ],
}


def sheet(overview=OVERVIEW):
    return _run(f"console.log(JSON.stringify(budgetSheet({json.dumps(overview)})));")


def test_euros_are_french_with_cents_only_when_needed_and_a_true_minus_sign():
    out = _run("console.log(JSON.stringify([923.15, -100.69, 1000, 0, -0.004, 12345.5].map(formatEuros)));")
    assert out == [f"923,15{NBSP}€", f"−100,69{NBSP}€", f"1{NNBSP}000{NBSP}€", f"0{NBSP}€", f"0{NBSP}€",
                   f"12{NNBSP}345,50{NBSP}€"]


def test_header_names_the_active_month_and_the_saved_amount():
    out = sheet()
    assert out["title"] == "novembre 2026"
    assert out["saved"] == {"text": f"2{NNBSP}012,35{NBSP}€", "tone": "ok"}
    negative = sheet({**OVERVIEW, "saved": -370.84})
    assert negative["saved"]["tone"] == "danger"


def test_chart_pairs_expenses_and_income_per_month_scaled_on_the_highest_bar():
    chart = sheet()["chart"]
    assert [(b["axis"], b["current"]) for b in chart] == [("S", False), ("O", False), ("N", True)]
    assert chart[1]["expenses"] == {"value": "4,8k", "pct": 100}
    assert chart[1]["income"] == {"value": "4,5k", "pct": 92}
    assert chart[2]["expenses"] == {"value": "203", "pct": 4}
    assert chart[2]["label"] == f"novembre : dépenses 203,20{NBSP}€, revenus 2{NNBSP}215,55{NBSP}€"


def test_chart_without_amounts_has_flat_bars():
    chart = sheet({**OVERVIEW, "series": [month(1, 0, 0)]})["chart"]
    assert chart[0]["expenses"]["pct"] == 0 and chart[0]["income"]["pct"] == 0


def test_groups_keep_their_order_and_total_negative_total_in_red():
    groups = sheet()["groups"]
    assert [(g["name"], g["total"]) for g in groups] == [
        ("Courants", {"text": f"404,91{NBSP}€", "tone": "default"}),
        ("Loisir", {"text": f"120{NBSP}€", "tone": "default"}),
    ]
    assert all("kind" not in g for g in groups)
    red = sheet({**OVERVIEW, "groups": [{**OVERVIEW["groups"][0], "total_remaining": -1307.18}]})
    assert red["groups"][0]["total"]["tone"] == "danger"


def test_expense_category_shows_remaining_month_detail_and_progress():
    course, restaurant, voiture, imprevu = sheet()["groups"][0]["categories"]
    assert course == {
        "name": "Course", "remaining": {"text": f"923,15{NBSP}€", "tone": "default"},
        "detail": f"ce mois : dépensé 76,02{NBSP}€ / budget 1{NNBSP}000{NBSP}€", "pct": 8, "over": False,
    }
    assert restaurant["remaining"]["tone"] == "danger"
    assert (restaurant["pct"], restaurant["over"]) == (100, True)
    assert (voiture["pct"], voiture["over"]) == (0, False)
    assert (imprevu["pct"], imprevu["over"]) == (100, True)  # dépense sans budget
