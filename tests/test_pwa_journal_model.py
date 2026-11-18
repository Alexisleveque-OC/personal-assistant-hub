"""Refonte UX (ROADMAP Étape 7 suite) : feuille « Journal & feedback » — logique d'affichage pure.

`journal_model.js` (sans DOM) est exécuté sous Node avec `db_date.js` (date de la base, UTC → heure de Paris).
Contenu inchangé : statut, intention, date, requête, réponse, latence, modèle, correction pour l'auto-apprentissage.
Les champs lus sont ceux de l'API (`success`, `raw_query`, `error_trace`, `llm_model`), pas ceux de l'ancienne vue.
"""
import json

from tests.js_helpers import js_source, run_node

NOW = "2026-11-17T12:00:00Z"


def _run(snippet: str):
    return run_node(js_source("db_date.js", "journal_model.js", strip_imports=True) + "\n" + snippet)


def log(**extra):
    base = {"id": 36, "raw_query": "modifie le RPE de ma dernière séance à 8", "intent": "agent",
            "spoken_response": "C'est noté : RPE 8.", "success": True, "latency_ms": 2013.07,
            "llm_model": "gemini-3.5-flash-lite", "error_trace": None, "created_at": "2026-10-27 09:56:56"}
    return {**base, **extra}


def card(entry):
    return _run(f"console.log(JSON.stringify(logCard({json.dumps(entry)}, new Date('{NOW}'))));")


def test_card_reads_the_api_fields():
    out = card(log())
    assert out == {
        "id": 36, "ok": True, "status": "Réussi", "intent": "agent", "date": "27 oct. · 10:56",
        "query": "modifie le RPE de ma dernière séance à 8", "reply": "C'est noté : RPE 8.",
        "meta": "2,0 s · gemini-3.5-flash-lite",
    }


def test_failed_exchange_shows_the_error_when_otis_said_nothing():
    out = card(log(success=False, spoken_response="", error_trace="TimeoutError: Gemini", latency_ms=0, llm_model=None))
    assert (out["ok"], out["status"], out["reply"], out["meta"]) == (False, "Échec", "TimeoutError: Gemini", "")


def test_latency_formats_and_no_invented_model():
    metas = [card(log(latency_ms=ms, llm_model=None))["meta"] for ms in (1.8, 20.63, 192.54, 999.6, 12500)]
    assert metas == ["1,8 ms", "21 ms", "193 ms", "1,0 s", "12,5 s"]


def test_empty_reply_and_query():
    out = card(log(raw_query="", spoken_response="", error_trace=None))
    assert (out["query"], out["reply"]) == ("—", "Aucune réponse")


def test_feedback_payload_is_a_trimmed_correction_or_nothing():
    out = _run("console.log(JSON.stringify([feedbackPayload('  Il fallait 9  '), feedbackPayload('   ')]));")
    assert out == [{"feedback_type": "correction", "user_note": "Il fallait 9"}, None]
