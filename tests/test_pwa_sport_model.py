"""Refonte UX (ROADMAP Étape 2) : feuille Sport — logique d'affichage et formulaire Séance.

Le module `sport_model.js` (sans import ni DOM) est exécuté sous Node."""
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
    source = (STATIC / "js" / "sport_model.js").read_text(encoding="utf-8") + "\n" + snippet
    result = subprocess.run([NODE, "--input-type=module"], input=source, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


SESSION = """{
  id: 12, date: "2026-11-09", semaine: 46, statut: "Réalisé", type_seance: "Sortie Longue",
  distance_km: 7.01, denivele_d_plus: 29, duree_secondes: 2757, ressenti_rpe: 6, meteo_note: 2,
  fc_moyenne: null, fc_max: null, remarques: "Grosse douleur au genou droit", programme: "",
  strava_id: "123", douleur_intensite: null, douleur_zone: null, charge_rpe: 276, km_effort: 7.3 }"""


# ---------- Formats ----------

def test_formats_follow_the_mockups():
    out = _run("""
console.log(JSON.stringify([
  formatKm(7.01), formatKm(568.5), formatKm(5), formatKm(7.456),
  formatClock(2757), formatClock(3723), formatClock(null), formatClock(0),
  shortDay("2026-11-09"), longDay("2026-11-09"),
  weekRange("2026-11-09", "2026-11-15"), weekRange("2026-11-30", "2026-12-06"), weekRange("2025-12-29", "2026-01-04"),
  isoWeekOf("2026-11-09"), isoWeekOf("2026-01-01"), formatThousands(10413),
]));
""")
    assert out == [
        "7,01", "568,5", "5", "7,46",
        "45:57", "1:02:03", "", "",
        "Lun. 9", "Lun. 9 nov.",
        "9 – 15 nov.", "30 nov. – 6 déc.", "29 déc. – 4 janv.",
        {"week": 46, "year": 2026}, {"week": 1, "year": 2026}, "10 413",
    ]


def test_types_offer_the_six_proposed_choices_and_keep_labels_for_old_types():
    out = _run("""
console.log(JSON.stringify([
  TYPE_CHOICES.map((t) => t.value), TYPE_CHOICES.map((t) => t.label),
  ["EF", "Sortie Longue", "Vitesse", "Renforcement", "Fractionné", "Course", "Tempo", "Récup"].map((t) => [typeLabel(t), typeEmoji(t)]),
]));
""")
    assert out == [
        ["EF", "Course", "Sortie Longue", "Vitesse", "Fractionné", "Renforcement"],
        ["Endurance", "Course", "Sortie longue", "Vitesse", "Fractionné", "Renforcement"],
        [["Endurance", "🏃"], ["Sortie longue", "🏔️"], ["Vitesse", "🚀"], ["Renforcement", "💪"],
         ["Fractionné", "⚡"], ["Course", "👟"], ["Tempo", "🔥"], ["Récup", "🌱"]],
    ]


# ---------- Douleur ----------

def test_pain_tag_uses_the_stored_fields_otherwise_guesses_from_remarks():
    out = _run("""
const base = { remarques: "", douleur_intensite: null, douleur_zone: null };
console.log(JSON.stringify([
  painTag({ ...base, douleur_intensite: 6, douleur_zone: "Tibia / genou" }),
  painTag({ ...base, douleur_intensite: 4 }),
  painTag({ ...base, douleur_intensite: 0, remarques: "douleur au genou" }),
  painTag({ ...base, remarques: "Petite douleur au tibia" }),
  painTag({ ...base, remarques: "Super sortie" }),
]));
""")
    assert out == ["Tibia / genou · 6/10", "Douleur 4/10", None, "Douleur ?", None]


# ---------- Vue Semaine ----------

def test_health_badge_comes_from_the_existing_safety_alert():
    out = _run("""
console.log(JSON.stringify([
  healthBadge("🟢 Progression Saine (+3.2%)"), healthBadge("🟢 Première semaine enregistrée"),
  healthBadge("🟡 Vigilance (+12.0%)"), healthBadge("🔴 Risque Blessure (+20.0%)"), healthBadge(null),
]));
""")
    assert out == [
        {"label": "Saine", "tone": "ok"}, {"label": "Saine", "tone": "ok"},
        {"label": "Vigilance", "tone": "warn"}, {"label": "Risque", "tone": "danger"}, None,
    ]


def test_week_gauge_compares_km_effort_to_the_week_ceiling():
    out = _run("""
console.log(JSON.stringify([weekGauge(7.3, 11.6), weekGauge(14, 11.6), weekGauge(7.3, null)]));
""")
    assert out == [
        {"pct": 63, "over": False, "value": "7,3 km‑effort", "limit": "Plafond : 11,6 km‑eff"},
        {"pct": 100, "over": True, "value": "14 km‑effort", "limit": "Plafond : 11,6 km‑eff"},
        None,
    ]


def test_week_period_label_and_navigation():
    out = _run("""
const week = { scale: "week", start_date: "2026-11-09", end_date: "2026-11-15", label: "Semaine 46 · 2026" };
const month = { scale: "month", start_date: "2026-10-01", end_date: "2026-10-31", label: "Octobre 2026" };
const year = { scale: "year", start_date: "2025-01-01", end_date: "2025-12-31", label: "Saison 2025" };
console.log(JSON.stringify([
  periodLabel(week), periodLabel(month), periodLabel(year),
  isCurrentPeriod(week, "2026-11-16"), isCurrentPeriod(week, "2026-11-12"),
  previousRef(week), nextRef(week), previousRef(month), nextRef(year),
]));
""")
    assert out == [
        {"title": "Semaine 46", "sub": "9 – 15 nov."},
        {"title": "Octobre 2026", "sub": ""},
        {"title": "2025", "sub": ""},
        False, True,
        "2026-11-08", "2026-11-16", "2026-09-30", "2026-01-01",
    ]


def test_session_row_summarises_a_session_for_the_lists():
    out = _run(f"""
const s = {SESSION};
const renfo = {{ ...s, id: 3, date: "2026-11-03", type_seance: "Renforcement", distance_km: null, duree_secondes: 1800,
  ressenti_rpe: 9, meteo_note: null, remarques: "", denivele_d_plus: 0 }};
const planned = {{ ...s, id: 4, date: "2026-11-14", statut: "Prévu", distance_km: 10, duree_secondes: null,
  ressenti_rpe: null, meteo_note: null, remarques: "" }};
console.log(JSON.stringify([sessionRow(s), sessionRow(renfo), sessionRow(planned)]));
""")
    assert out == [
        {"id": 12, "emoji": "🏔️", "title": "Lun. 9 · Sortie longue", "summary": "7,01 km · 45:57 · RPE 6",
         "feel": "RPE 6 · météo 2/10", "value": "7,01", "unit": "km", "pain": "Douleur ?", "planned": False},
        {"id": 3, "emoji": "💪", "title": "Mar. 3 · Renforcement", "summary": "30:00 · RPE 9",
         "feel": "RPE 9", "value": "30", "unit": "min", "pain": None, "planned": False},
        {"id": 4, "emoji": "🏔️", "title": "Sam. 14 · Sortie longue", "summary": "Prévue · 10 km",
         "feel": "Prévue", "value": "10", "unit": "km", "pain": None, "planned": True},
    ]


def test_sessions_are_grouped_by_iso_week_with_the_year_when_not_current():
    out = _run("""
const sessions = [
  { id: 1, date: "2026-11-09" }, { id: 2, date: "2026-11-05" }, { id: 3, date: "2026-11-03" },
  { id: 4, date: "2025-12-29" }, { id: 5, date: "2025-12-20" } ];
console.log(JSON.stringify(groupByWeek(sessions, 2026).map((g) => [g.label, g.sessions.map((s) => s.id)])));
""")
    assert out == [["Semaine 46", [1]], ["Semaine 45", [2, 3]], ["Semaine 1", [4]], ["Semaine 51 · 2025", [5]]]


# ---------- Vue Mois · Année ----------

def test_year_chart_stops_at_the_current_month_and_opens_a_month():
    out = _run("""
const months = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
const series = months.map((label, i) => ({ label, distance_km: [20, 25, 61, 77, 57, 54, 54, 64, 73, 40, 10, 0][i], is_current: i === 10 }));
const dash = { scale: "year", start_date: "2026-01-01", end_date: "2026-12-31", series };
const bars = chartBars(dash, "2026-11-16");
const past = chartBars({ ...dash, start_date: "2025-01-01", end_date: "2025-12-31" }, "2026-11-16");
console.log(JSON.stringify([bars.length, bars[0], bars[3], bars[10], past.length]));
""")
    assert out == [
        11,
        {"axis": "J", "value": "20", "pct": 26, "current": False, "ref": "2026-01-01", "scale": "month"},
        {"axis": "A", "value": "77", "pct": 100, "current": False, "ref": "2026-04-01", "scale": "month"},
        {"axis": "N", "value": "10", "pct": 13, "current": True, "ref": "2026-11-01", "scale": "month"},
        12,
    ]


def test_month_chart_has_one_bar_per_week_opening_that_week():
    out = _run("""
const series = [ { label: "S44", distance_km: 12.4, is_current: false }, { label: "S45", distance_km: 0, is_current: false },
  { label: "S46", distance_km: 7.01, is_current: true } ];
const dash = { scale: "month", start_date: "2026-11-01", end_date: "2026-11-30", series };
console.log(JSON.stringify(chartBars(dash, "2026-11-16")));
""")
    assert out == [
        {"axis": "S44", "value": "12", "pct": 100, "current": False, "ref": "2026-11-01", "scale": "week"},
        {"axis": "S45", "value": "0", "pct": 0, "current": False, "ref": "2026-11-02", "scale": "week"},
        {"axis": "S46", "value": "7", "pct": 57, "current": True, "ref": "2026-11-09", "scale": "week"},
    ]


# ---------- Détail d'une séance ----------

def test_detail_shows_chips_subtitle_and_tiles():
    out = _run(f"""
const s = {SESSION};
console.log(JSON.stringify([detailSubtitle(s), detailSubtitle({{ ...s, strava_id: null }}), detailChips(s), detailTiles(s)]));
""")
    subtitle, manual, chips, tiles = out
    assert subtitle == "Semaine 46 · import Strava"
    assert manual == "Semaine 46"
    assert chips == [
        {"text": "🏔️ Sortie longue", "tone": "warn"},
        {"text": "Réalisée", "tone": "ok"},
        {"text": "Douleur ?", "tone": "danger"},
    ]
    assert [(t["label"], t["value"], t["unit"], t["empty"], t["editable"]) for t in tiles] == [
        ("Distance", "7,01", "km", False, True),
        ("Durée", "45:57", "", False, True),
        ("Allure", "6:33", "", False, False),
        ("Dénivelé", "+29", "m", False, True),
        ("Ressenti", "6", "/10", False, True),
        ("Météo", "2", "/10", False, True),
        ("FC moy.", "Ajouter", "", True, True),
        ("FC max", "Ajouter", "", True, True),
        ("Charge", "276", "", False, False),
    ]


# ---------- Formulaire Séance ----------

def test_form_starts_empty_for_a_new_session_and_filled_for_an_edit():
    out = _run(f"""
console.log(JSON.stringify([emptyForm("2026-11-16"), sessionToForm({SESSION})]));
""")
    new, edit = out
    assert new == {
        "id": None, "date": "2026-11-16", "type": "EF", "statut": "Réalisé", "distance": "", "dplus": "",
        "h": "", "m": "", "s": "", "rpe": None, "meteo": None, "fcMoy": "", "fcMax": "",
        "remarques": "", "programme": "", "pain": False, "painLevel": 5, "painZone": "", "hadPain": False,
    }
    assert edit == {
        "id": 12, "date": "2026-11-09", "type": "Sortie Longue", "statut": "Réalisé", "distance": "7,01", "dplus": "29",
        "h": "0", "m": "45", "s": "57", "rpe": 6, "meteo": 2, "fcMoy": "", "fcMax": "",
        "remarques": "Grosse douleur au genou droit", "programme": "", "pain": False, "painLevel": 5, "painZone": "",
        "hadPain": False,
    }


def test_form_pace_is_computed_from_distance_and_duration():
    out = _run("""
const f = { ...emptyForm("2026-11-16"), distance: "7,01", h: "0", m: "45", s: "57" };
console.log(JSON.stringify([formPace(f), formPace({ ...f, distance: "" }), formPace({ ...f, m: "", s: "" })]));
""")
    assert out == ["Allure calculée : 6:33 /km", "", ""]


def test_form_payload_parses_french_numbers_and_skips_untouched_values():
    out = _run("""
const f = { ...emptyForm("2026-11-16"), type: "Vitesse", distance: "5,5", dplus: "40", h: "", m: "32", s: "5",
  rpe: 7, fcMoy: "151", remarques: "  Bien  ", programme: "6 x 400 m" };
console.log(JSON.stringify(formToPayload(f)));
""")
    assert out == {
        "errors": [],
        "payload": {
            "date": "2026-11-16", "type_seance": "Vitesse", "statut": "Réalisé", "distance_km": 5.5,
            "denivele_d_plus": 40, "duree_secondes": 1925, "ressenti_rpe": 7, "fc_moyenne": 151,
            "remarques": "Bien", "programme": "6 x 400 m",
        },
    }


def test_form_payload_reports_each_invalid_field():
    out = _run("""
const f = { ...emptyForm(""), distance: "abc", m: "75", fcMax: "12" };
console.log(JSON.stringify(formToPayload(f).errors));
""")
    assert out == [
        "Date : choisis le jour de la séance.",
        "Distance : nombre attendu (ex. 7,01).",
        "Durée : minutes et secondes de 0 à 59.",
        "FC max : entre 30 et 250 bpm.",
    ]


def test_form_payload_sends_pain_and_clears_it_when_unticked():
    out = _run(f"""
const withPain = {{ ...emptyForm("2026-11-16"), pain: true, painLevel: 6, painZone: " Tibia / genou " }};
const edited = sessionToForm({{ ...{SESSION}, douleur_intensite: 6, douleur_zone: "Tibia" }});
const cleared = {{ ...edited, pain: false }};
const noPain = sessionToForm({SESSION});
const p = (f) => formToPayload(f).payload;
console.log(JSON.stringify([
  [p(withPain).douleur_intensite, p(withPain).douleur_zone],
  [edited.pain, edited.painLevel, edited.painZone, edited.hadPain],
  [p(cleared).douleur_intensite, p(cleared).douleur_zone],
  ["douleur_intensite" in p(noPain), "douleur_zone" in p(noPain)],
]));
""")
    assert out == [[6, "Tibia / genou"], [True, 6, "Tibia", True], [0, ""], [False, False]]


def test_draft_prefills_only_the_fields_otis_understood():
    out = _run("""
const f = { ...emptyForm("2026-11-16"), remarques: "déjà écrit" };
const draft = { date: "2026-11-15", type_seance: "Fractionné", distance_km: 8.2, duree_secondes: 3015,
  ressenti_rpe: 8, meteo_note: 3, douleur_intensite: 4, douleur_zone: "mollet", remarques: "Dur mais bien", statut: "Réalisé" };
console.log(JSON.stringify([applyDraft(f, draft), applyDraft(f, {})]));
""")
    filled, untouched = out
    assert filled == {
        "id": None, "date": "2026-11-15", "type": "Fractionné", "statut": "Réalisé", "distance": "8,2", "dplus": "",
        "h": "0", "m": "50", "s": "15", "rpe": 8, "meteo": 3, "fcMoy": "", "fcMax": "",
        "remarques": "Dur mais bien", "programme": "", "pain": True, "painLevel": 4, "painZone": "mollet", "hadPain": False,
    }
    assert untouched["remarques"] == "déjà écrit"


def test_chart_follows_the_selected_tile_metric():
    out = _run("""
const series = [
  { label: "janv.", distance_km: 20, km_effort: 22.5, vitesse_kmh: 9.0, charge_rpe: 900, is_current: false },
  { label: "févr.", distance_km: 10, km_effort: 10.4, vitesse_kmh: 10.0, charge_rpe: 1200, is_current: false },
  { label: "mars", distance_km: 0, km_effort: 0, vitesse_kmh: null, charge_rpe: 0, is_current: false } ];
const dash = { scale: "year", start_date: "2025-01-01", end_date: "2025-12-31", series };
const pick = (metric) => chartBars(dash, "2026-11-16", metric).slice(0, 3).map((b) => [b.value, b.pct]);
console.log(JSON.stringify([pick("effort"), pick("allure"), pick("charge"), CHART_METRICS]));
""")
    effort, allure, charge, metrics = out
    assert effort == [["23", 100], ["10", 46], ["0", 0]]
    assert allure == [["6:40", 90], ["6:00", 100], ["", 0]]  # barre = vitesse, libellé = allure
    assert charge == [["900", 75], ["1 200", 100], ["0", 0]]
    assert metrics == {
        "volume": "Volume (km)", "effort": "km‑effort", "allure": "Allure (min/km)", "charge": "Charge RPE",
    }


def test_tapping_a_scale_pill_selects_it_and_tapping_it_again_clears_it_when_allowed():
    out = _run("""
console.log(JSON.stringify([
  nextScaleValue(null, 6, true), nextScaleValue(6, 8, true), nextScaleValue(6, 6, true),
  nextScaleValue(6, 6, false), nextScaleValue(6, 0, false),
]));
""")
    assert out == [6, 8, None, 6, 0]
