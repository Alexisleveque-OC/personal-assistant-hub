"""Phase 10, étape 7b : formulaire Dépense / Revenu — logique pure (`budget_form_model.js`, sous Node).

Décisions du 26/11 : onglets Dépense | Revenu ; montant, catégorie (liste), date (aujourd'hui par défaut), libellé
obligatoire ; Dépense : remboursement (ligne négative) et Débit / Swile. Revenu : types du groupe Revenus.
"""
from tests.js_helpers import js_source, run_node

OVERVIEW = {
    "groups": [
        {"name": "Courants", "categories": [{"name": "Course"}, {"name": "Restaurant"}]},
        {"name": "Loisir", "categories": [{"name": "Loisir Alex"}]},
    ],
    "income_categories": ["Salaire Alexis", "CAF"],
}


def _run(snippet: str):
    return run_node(js_source("budget_form_model.js") + "\n" + snippet)


def test_empty_form_is_an_expense_of_today_on_the_bank_account():
    assert _run('console.log(JSON.stringify(emptyBudgetForm("2026-11-26")));') == {
        "type": "depense", "montant": "", "categorie": "", "libelle": "", "date": "2026-11-26",
        "swile": False, "remboursement": False,
    }


def test_expense_choices_are_grouped_like_the_list_and_income_choices_come_from_revenus():
    out = _run(f"""
const o = {__import__("json").dumps(OVERVIEW)};
console.log(JSON.stringify([categoryChoices(o, "depense"), categoryChoices(o, "revenu"), categoryChoices({{}}, "revenu")]));
""")
    assert out == [
        [{"group": "Courants", "names": ["Course", "Restaurant"]}, {"group": "Loisir", "names": ["Loisir Alex"]}],
        [{"group": "Revenus", "names": ["Salaire Alexis", "CAF"]}],
        [{"group": "Revenus", "names": []}],
    ]


def test_valid_expense_becomes_the_api_payload_with_a_decimal_comma():
    out = _run("""
const form = { ...emptyBudgetForm("2026-11-26"), montant: " 12,50 ", categorie: "Course", libelle: " pain ",
  swile: true, remboursement: true };
console.log(JSON.stringify(budgetFormToPayload(form, "pwa-1")));
""")
    assert out == {"errors": [], "payload": {
        "type": "depense", "montant": 12.5, "categorie": "Course", "libelle": "pain", "date": "2026-11-26",
        "swile": True, "remboursement": True, "session_id": "pwa-1",
    }}


def test_income_never_sends_swile_or_refund():
    out = _run("""
const form = { ...emptyBudgetForm("2026-11-26"), type: "revenu", montant: "151.05", categorie: "CAF", libelle: "CAF",
  swile: true, remboursement: true };
console.log(JSON.stringify(budgetFormToPayload(form, "pwa-1").payload));
""")
    assert out["swile"] is False and out["remboursement"] is False and out["montant"] == 151.05


def test_missing_or_invalid_fields_are_listed_in_french():
    out = _run("""
const bad = { ...emptyBudgetForm(""), montant: "douze" };
const zero = { ...emptyBudgetForm("2026-11-26"), montant: "0", categorie: "Course", libelle: "x" };
console.log(JSON.stringify([budgetFormToPayload(bad, "s"), budgetFormToPayload(zero, "s").errors]));
""")
    assert out[0] == {"errors": ["Montant invalide (ex. 12,50).", "Choisis une catégorie.", "Écris un libellé.",
                                 "Choisis une date."], "payload": None}
    assert out[1] == ["Montant invalide (ex. 12,50)."]
