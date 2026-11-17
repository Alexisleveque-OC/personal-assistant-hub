"""Refonte UX (ROADMAP Étape 7 suite) : feuille « Réglages & voix » — encart « Modèle & quotas Gemini » (logique pure).

`settings_model.js` (sans import ni DOM) est exécuté sous Node. Contenu inchangé par rapport à l'ancienne modale.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
WINDOWS_NODE = Path("/mnt/c/Program Files/nodejs/node.exe")
NODE = shutil.which("node") or (str(WINDOWS_NODE) if WINDOWS_NODE.exists() else None)


def stats(data):
    if not NODE:
        pytest.skip("Node.js indisponible pour exécuter le module JS")
    source = (STATIC / "js" / "settings_model.js").read_text(encoding="utf-8")
    source += f"\nconsole.log(JSON.stringify(llmStatsView({json.dumps(data)})));"
    result = subprocess.run([NODE, "--input-type=module"], input=source, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


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
