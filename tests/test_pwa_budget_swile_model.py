"""Phase 10, étape 8 (4/4) : relecture de l'import Swile — logique pure (`budget_swile_model.js`, sous Node).

Décisions du 26/11 : lignes à cocher (doublons décochés), catégorie pré-remplie et modifiable par le champ à
suggestions (types du groupe Revenus pour un crédit), solde « ancien → nouveau » coché par défaut ; le bouton dit
combien de lignes seront importées ; une ligne cochée sans catégorie de la liste bloque l'envoi.
"""
import json

from tests.js_helpers import js_source, run_node

OVERVIEW = {
    "groups": [
        {"name": "Courants", "categories": [{"name": "Course"}, {"name": "Restaurant"}]},
        {"name": "Loisir", "categories": [{"name": "Cadeaux Elias "}]},
    ],
    "income_categories": ["Salaire Alexis", "Ticket resto"],
}
REVIEW = {
    "lignes": [
        {"type": "depense", "date": "2026-11-25", "montant": 12.81, "marchand": "Intermarche", "categorie": "Course",
         "doublon": None, "cochee": True},
        {"type": "depense", "date": "2026-11-23", "montant": 6.9, "marchand": "Maryann", "categorie": None,
         "doublon": None, "cochee": True},
        {"type": "depense", "date": "2026-11-21", "montant": 25.0, "marchand": "Intermarche", "categorie": "Course",
         "doublon": "déjà saisie le 22/11 (Course) ?", "cochee": False},
        {"type": "credit", "date": "2026-11-06", "montant": 242.0, "marchand": "Crédit titres-resto",
         "categorie": "Ticket resto", "doublon": None, "cochee": True},
    ],
    "solde": {"nouveau": 95.64, "actuel": 80.0, "mois": "novembre 2026"},
    "avertissements": ["Ligne illisible ignorée : Fnac (« Hier », 0,00 €)."],
}


def _run(snippet: str):
    source = js_source("budget_model.js", "budget_form_model.js", "budget_swile_model.js", strip_imports=True)
    return run_node(source + f"\nconst review = {json.dumps(REVIEW)};\nconst overview = {json.dumps(OVERVIEW)};\n" + snippet)


def test_review_becomes_an_editable_state_with_the_balance_checked():
    out = _run("console.log(JSON.stringify(swileState(review)));")
    assert [(l["checked"], l["categorie"]) for l in out["lines"]] == [
        (True, "Course"), (True, ""), (False, "Course"), (True, "Ticket resto"),
    ]
    assert out["balance"] == {"nouveau": 95.64, "actuel": 80.0, "mois": "novembre 2026", "checked": True}
    assert out["warnings"] == REVIEW["avertissements"]


def test_line_texts_show_date_amount_and_the_duplicate_question():
    out = _run("console.log(JSON.stringify(swileState(review).lines.map(swileLineTexts)).replaceAll('\\u00a0', ' '));")
    assert out[0] == {"title": "Intermarche", "meta": "25/11 · 12,81 €", "note": ""}
    assert out[2]["note"] == "déjà saisie le 22/11 (Course) ?"
    assert out[3] == {"title": "Crédit titres-resto", "meta": "06/11 · +242 €", "note": "Crédit → Revenus"}


def test_balance_text_says_old_and_new_values():
    out = _run("""
const s = swileState(review);
console.log(JSON.stringify([swileBalanceText(s.balance), swileBalanceText({ ...s.balance, actuel: null })]));
""")
    assert [t.replace("\xa0", " ") for t in out] == [
        "Reste Swile (novembre 2026) : 80 € → 95,64 €",
        "Reste Swile (novembre 2026) : vide → 95,64 €",
    ]


def test_button_label_counts_what_will_be_imported():
    out = _run("""
const s = swileState(review);
const none = { ...s, lines: s.lines.map((l) => ({ ...l, checked: false })) };
console.log(JSON.stringify([
  swileImportLabel(s),
  swileImportLabel({ ...s, balance: { ...s.balance, checked: false } }),
  swileImportLabel(none),
  swileImportLabel({ ...none, balance: null }),
  swileImportLabel({ ...none, balance: null, lines: [{ ...s.lines[0], checked: true }] }),
]));
""")
    assert out == [
        "Importer 3 lignes et le solde", "Importer 3 lignes", "Importer le solde", "Rien à importer",
        "Importer 1 ligne",
    ]


def test_checked_lines_need_a_category_from_the_list_of_their_kind():
    out = _run("""
const s = swileState(review);
s.lines[0].categorie = "ticket resto";  // type de revenu proposé à une dépense : refusé
console.log(JSON.stringify(swileToPayload(s, "pwa-1", overview)));
""")
    assert out["payload"] is None
    assert out["errors"] == [
        "Intermarche (25/11) : choisis une catégorie dans la liste.",
        "Maryann (23/11) : choisis une catégorie.",
    ]


def test_payload_keeps_checked_lines_with_exact_names_and_the_checked_balance():
    out = _run("""
const s = swileState(review);
s.lines[1].categorie = " restaurant ";
s.lines[2].checked = true;  // doublon recoché : c'était bien un 2e achat
const first = swileToPayload(s, "pwa-1", overview);
s.balance.checked = false;
s.lines.forEach((l) => { l.checked = false; });
console.log(JSON.stringify([first, swileToPayload(s, "pwa-1", overview)]));
""")
    first, nothing = out
    assert first["errors"] == []
    assert first["payload"] == {
        "lignes": [
            {"type": "depense", "date": "2026-11-25", "montant": 12.81, "marchand": "Intermarche", "categorie": "Course"},
            {"type": "depense", "date": "2026-11-23", "montant": 6.9, "marchand": "Maryann", "categorie": "Restaurant"},
            {"type": "depense", "date": "2026-11-21", "montant": 25.0, "marchand": "Intermarche", "categorie": "Course"},
            {"type": "credit", "date": "2026-11-06", "montant": 242.0, "marchand": "Crédit titres-resto",
             "categorie": "Ticket resto"},
        ],
        "solde": 95.64,
        "session_id": "pwa-1",
    }
    assert nothing == {"errors": ["Coche au moins une ligne ou le solde."], "payload": None}
