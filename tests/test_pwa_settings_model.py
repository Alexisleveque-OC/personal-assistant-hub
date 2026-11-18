"""Refonte UX (ROADMAP Étape 7 suite) : feuille « Réglages & voix » — encart « Modèle & quotas Gemini » (logique pure).

`settings_model.js` (sans import ni DOM) est exécuté sous Node. Contenu inchangé par rapport à l'ancienne modale.
"""
import json

from tests.js_helpers import STATIC, run_node



def stats(data):
    source = (STATIC / "js" / "settings_model.js").read_text(encoding="utf-8")
    source += f"\nconsole.log(JSON.stringify(llmStatsView({json.dumps(data)})));"
    return run_node(source)


def usage(**extra):
    return {"model": "gemini-3.5-flash-lite", "daily_requests": 12, "max_daily_requests": 1000,
            "remaining_daily_requests": 988, "last_latency_ms": 2013.07, "quota_exceeded": False, **extra}


def test_active_quota():
    assert stats(usage()) == {
        "model": "gemini-3.5-flash-lite", "requests": "12 / 1000", "remaining": "988 restantes",
        "latency": "2013 ms", "badge": {"text": "Actif", "tone": "ok"},
    }


def test_low_and_exceeded_quota():
    assert stats(usage(remaining_daily_requests=99))["badge"] == {"text": "Attention", "tone": "warn"}
    assert stats(usage(remaining_daily_requests=0, quota_exceeded=True))["badge"] == {"text": "Quota atteint", "tone": "danger"}


def test_no_request_yet_and_unknown_model():
    out = stats(usage(model=None, last_latency_ms=None))
    assert (out["model"], out["latency"]) == ("Indisponible", "Aucune requête")


def test_stats_unavailable():
    assert stats(None) == {
        "model": "Indisponible", "requests": "—", "remaining": "—", "latency": "—",
        "badge": {"text": "Indisponible", "tone": "muted"},
    }
