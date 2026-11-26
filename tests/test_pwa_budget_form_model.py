"""Phase 10, étape 7b : formulaire Dépense / Revenu — logique pure (`budget_form_model.js`, sous Node).

Décisions du 26/11 : onglets Dépense | Revenu ; montant, catégorie (liste), date (aujourd'hui par défaut), libellé
obligatoire ; Dépense : remboursement (ligne négative) et Débit / Swile. Revenu : types du groupe Revenus.
Retour du 26/11 : la liste déroulante était trop longue → champ texte avec suggestions (« cour » → Course), sans
accents ni casse ; un nom tapé en entier suffit, un nom hors liste est refusé avant l'envoi.
"""
from tests.js_helpers import js_source, run_node

OVERVIEW = {
    "groups": [
        {"name": "Courants", "categories": [{"name": "Course"}, {"name": "Restaurant"}]},
        {"name": "Loisir", "categories": [{"name": "Loisir Alex"}, {"name": "Cadeaux Elias "}]},
        {"name": "Epargne", "categories": [{"name": "épargne Candice"}, {"name": "Recours"}]},
    ],
    "income_categories": ["Salaire Alexis", "CAF"],
}


def _run(snippet: str):
    return run_node(js_source("budget_form_model.js") + "\n" + snippet)


def test_empty_form_is_an_expense_of_today_on_the_bank_account():
    assert _run('console.log(JSON.stringify(emptyBudgetForm("2026-11-26")));') == {
        "type": "depense", "montant": "", "categorie": "", "libelle": "", "date": "2026-11-26",
        "swile": False, "remboursement": False,
        "nom": "", "nbEcheances": "", "moisDebut": "2026-11", "commentaire": "",
        "motCle": "", "parts": [{"categorie": "", "montant": ""}, {"categorie": "", "montant": ""}],
    }


def test_expense_choices_are_grouped_like_the_list_and_income_choices_come_from_revenus():
    out = _run(f"""
const o = {__import__("json").dumps(OVERVIEW)};
console.log(JSON.stringify([categoryChoices(o, "depense"), categoryChoices(o, "revenu"), categoryChoices({{}}, "revenu")]));
""")
    assert out == [
        [{"group": "Courants", "names": ["Course", "Restaurant"]},
         {"group": "Loisir", "names": ["Loisir Alex", "Cadeaux Elias "]},
         {"group": "Epargne", "names": ["épargne Candice", "Recours"]}],
        [{"group": "Revenus", "names": ["Salaire Alexis", "CAF"]}],
        [{"group": "Revenus", "names": []}],
    ]


def test_valid_expense_becomes_the_api_payload_with_a_decimal_comma():
    out = _run("""
const form = { ...emptyBudgetForm("2026-11-26"), montant: " 12,50 ", categorie: " COURSE ", libelle: " pain ",
  swile: true, remboursement: true };
console.log(JSON.stringify(budgetFormToPayload(form, "pwa-1", [{ group: "Courants", names: ["Course"] }])));
""")
    assert out == {"errors": [], "payload": {
        "type": "depense", "montant": 12.5, "categorie": "Course", "libelle": "pain", "date": "2026-11-26",
        "swile": True, "remboursement": True, "session_id": "pwa-1",
    }}


def test_income_never_sends_swile_or_refund():
    out = _run("""
const form = { ...emptyBudgetForm("2026-11-26"), type: "revenu", montant: "151.05", categorie: "CAF", libelle: "CAF",
  swile: true, remboursement: true };
console.log(JSON.stringify(budgetFormToPayload(form, "pwa-1", [{ group: "Revenus", names: ["CAF"] }]).payload));
""")
    assert out["swile"] is False and out["remboursement"] is False and out["montant"] == 151.05


def test_missing_or_invalid_fields_are_listed_in_french():
    out = _run("""
const bad = { ...emptyBudgetForm(""), montant: "douze" };
const zero = { ...emptyBudgetForm("2026-11-26"), montant: "0", categorie: "Course", libelle: "x" };
const choices = [{ group: "Courants", names: ["Course"] }];
const unknown = { ...zero, montant: "3", categorie: "cour" };
console.log(JSON.stringify([budgetFormToPayload(bad, "s", choices), budgetFormToPayload(zero, "s", choices).errors,
  budgetFormToPayload(unknown, "s", choices).errors]));
""")
    assert out[0] == {"errors": ["Montant invalide (ex. 12,50).", "Choisis une catégorie.", "Écris un libellé.",
                                 "Choisis une date."], "payload": None}
    assert out[1] == ["Montant invalide (ex. 12,50)."]
    assert out[2] == ["Choisis une catégorie dans la liste."]


def _matches(query, kind="depense"):
    return _run(f"""
const choices = categoryChoices({__import__("json").dumps(OVERVIEW)}, "{kind}");
console.log(JSON.stringify(matchCategories(choices, {__import__("json").dumps(query)})));
""")


def test_suggestions_ignore_accents_and_case_and_put_name_starts_first():
    assert _matches("cour") == [{"name": "Course", "group": "Courants"}, {"name": "Recours", "group": "Epargne"}]
    assert _matches("EPARG") == [{"name": "épargne Candice", "group": "Epargne"}]
    assert _matches("elias") == [{"name": "Cadeaux Elias", "group": "Loisir"}]  # espaces du classeur retirés
    assert _matches("  ") == [] and _matches("zzz") == []
    assert _matches("ca", "revenu") == [{"name": "CAF", "group": "Revenus"}]


def test_suggestions_are_capped_at_five():
    """Retour du 26/11 (téléphone) : le clavier masque le bas de la liste ; peu de lignes, champ remonté."""
    out = _run("""
const choices = [{ group: "G", names: Array.from({ length: 12 }, (_, i) => `Cat ${i}`) }];
console.log(JSON.stringify(matchCategories(choices, "cat").length));
""")
    assert out == 5



# --- Étape 7c : Échéancier et Dépense multiple (décisions du 26/11 : 4 onglets, « reste à répartir ») ---------------

CHOICES = 'categoryChoices({groups: [{name: "Courants", categories: [{name: "Course"}, {name: "Chats"}]}]}, "multiple")'


def test_installment_and_split_forms_choose_among_expense_categories():
    out = _run(f"console.log(JSON.stringify([{CHOICES}, categoryChoices({{groups: []}}, \"echeancier\")]));")
    assert out == [[{"group": "Courants", "names": ["Course", "Chats"]}], []]


def test_installment_payload_with_its_start_month():
    out = _run(f"""
const form = {{ ...emptyBudgetForm("2026-11-26"), type: "echeancier", nom: " ikea ", montant: "400", nbEcheances: "4",
  categorie: "course", moisDebut: "2026-12", commentaire: " canapé " }};
console.log(JSON.stringify(budgetFormToPayload(form, "pwa-1", {CHOICES})));
""")
    assert out == {"errors": [], "payload": {
        "nom": "ikea", "montant_total": 400, "nb_echeances": 4, "categorie": "Course", "mois_debut": "2026-12",
        "commentaire": "canapé", "session_id": "pwa-1",
    }}


def test_installment_errors_and_empty_start_month():
    out = _run(f"""
const bad = {{ ...emptyBudgetForm("2026-11-26"), type: "echeancier", nbEcheances: "1", moisDebut: "" }};
const ok = {{ ...bad, nom: "frigo", montant: "600", nbEcheances: "3", categorie: "Chats" }};
console.log(JSON.stringify([budgetFormToPayload(bad, "s", {CHOICES}).errors,
  budgetFormToPayload(ok, "s", {CHOICES}).payload.mois_debut]));
""")
    assert out == [["Écris un nom (magasin ou achat).", "Montant invalide (ex. 12,50).",
                    "Nombre d'échéances : 2 ou plus.", "Choisis une catégorie."], None]


def test_split_remainder_and_fill_the_rest_into_a_part():
    out = _run("""
const form = { ...emptyBudgetForm("2026-11-26"), type: "multiple", montant: "60,10",
  parts: [{ categorie: "Course", montant: "45" }, { categorie: "Chats", montant: "" }] };
const before = splitRemainder(form);
const filled = fillRemainder(form, 1);
const over = splitRemainder({ ...form, parts: [{ categorie: "Course", montant: "70" }] });
console.log(JSON.stringify([before, filled.parts[1].montant, splitRemainder(filled), over, form.parts[1].montant]));
""")
    assert out == [15.1, "15,10", 0, -9.9, ""]  # fillRemainder ne modifie pas le formulaire d'origine


def test_split_payload_and_its_errors():
    out = _run(f"""
const base = {{ ...emptyBudgetForm("2026-11-26"), type: "multiple", motCle: " amazon ", montant: "60" }};
const ok = {{ ...base, parts: [{{ categorie: "course", montant: "45" }}, {{ categorie: "Chats", montant: "15,00" }}] }};
const unbalanced = {{ ...base, parts: [{{ categorie: "Course", montant: "45" }}, {{ categorie: "Jardin", montant: "" }}] }};
const empty = {{ ...base, motCle: "", parts: [{{ categorie: "", montant: "" }}, {{ categorie: "", montant: "" }}] }};
console.log(JSON.stringify([budgetFormToPayload(ok, "s", {CHOICES}),
  budgetFormToPayload(unbalanced, "s", {CHOICES}).errors, budgetFormToPayload(empty, "s", {CHOICES}).errors]));
""")
    assert out[0] == {"errors": [], "payload": {
        "mot_cle": "amazon", "montant_total": 60, "date": "2026-11-26", "session_id": "s",
        "parts": [{"categorie": "Course", "montant": 45}, {"categorie": "Chats", "montant": 15}],
    }}
    assert out[1] == ["Part 2 : choisis une catégorie dans la liste.", "Part 2 : montant invalide.",
                      "Les parts font 45 € sur 60 € : il reste 15 € à répartir."]
    assert out[2] == ["Écris le mot-clé du relevé bancaire.", "Ajoute au moins une part."]
