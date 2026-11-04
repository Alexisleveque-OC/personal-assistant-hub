"""Journal du micro (ROADMAP Étape 0) : les événements du pipeline vocal sont gardés sur le téléphone
pour être relus depuis /static/audio_diag.html, sans câble USB ni console."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
MODULE_PATH = STATIC / "js" / "voice_diag_log.js"
WINDOWS_NODE = Path("/mnt/c/Program Files/nodejs/node.exe")
NODE = shutil.which("node") or (str(WINDOWS_NODE) if WINDOWS_NODE.exists() else None)

FAKE_STORAGE = """
class FakeStorage {
  constructor(initial = {}) { this.data = { ...initial }; }
  getItem(key) { return key in this.data ? this.data[key] : null; }
  setItem(key, value) { this.data[key] = String(value); }
  removeItem(key) { delete this.data[key]; }
}
const silentConsole = { debug() {}, warn(...args) { warnings.push(args.join(" ")); } };
const warnings = [];
let tick = 0;
const now = () => new Date(Date.UTC(2026, 10, 4, 8, 0, 0, tick++ * 10));
"""


def _run(snippet: str) -> dict:
    if not NODE:
        pytest.skip("Node.js indisponible pour exécuter le module JS")
    source = MODULE_PATH.read_text(encoding="utf-8") + "\n" + FAKE_STORAGE + "\n" + snippet
    result = subprocess.run([NODE, "--input-type=module"], input=source, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_module_is_served_as_javascript():
    res = client.get("/static/js/voice_diag_log.js")
    assert res.status_code == 200
    assert "javascript" in res.headers.get("content-type", "")


def test_record_appends_timestamped_entries_under_the_shared_key():
    out = _run("""
const storage = new FakeStorage();
const journal = createVoiceDiagLog({ storage, now, consoleSink: silentConsole });
journal.record("otis", "Chargement du moteur Vosk");
journal.record("dictée", "Micro ouvert en 420 ms");
console.log(JSON.stringify({ key: VOICE_DIAG_STORAGE_KEY, stored: JSON.parse(storage.getItem(VOICE_DIAG_STORAGE_KEY)) }));
""")
    assert out["key"] == "pah_voice_diag_log"
    assert out["stored"] == [
        {"at": "2026-11-04T08:00:00.000Z", "source": "otis", "message": "Chargement du moteur Vosk"},
        {"at": "2026-11-04T08:00:00.010Z", "source": "dictée", "message": "Micro ouvert en 420 ms"},
    ]


def test_journal_keeps_only_the_most_recent_entries():
    out = _run("""
const storage = new FakeStorage();
const journal = createVoiceDiagLog({ storage, now, max: 3, consoleSink: silentConsole });
for (let i = 1; i <= 5; i++) journal.record("envoi", `événement ${i}`);
console.log(JSON.stringify(journal.read().map((e) => e.message)));
""")
    assert out == ["événement 3", "événement 4", "événement 5"]


def test_corrupted_journal_is_reset_with_a_warning_instead_of_breaking_the_microphone():
    out = _run("""
const storage = new FakeStorage({ pah_voice_diag_log: "{pas du json" });
const journal = createVoiceDiagLog({ storage, now, consoleSink: silentConsole });
journal.record("otis", "après corruption");
console.log(JSON.stringify({ entries: journal.read().map((e) => e.message), warnings }));
""")
    assert out["entries"] == ["après corruption"]
    assert any("pah_voice_diag_log" in w for w in out["warnings"])


def test_failing_storage_is_reported_and_never_thrown_to_the_voice_pipeline():
    out = _run("""
const storage = new FakeStorage();
storage.setItem = () => { throw new Error("QuotaExceededError"); };
const journal = createVoiceDiagLog({ storage, now, consoleSink: silentConsole });
journal.record("dictée", "enregistrement");
console.log(JSON.stringify({ warnings }));
""")
    assert any("QuotaExceededError" in w for w in out["warnings"])


def test_clear_and_text_format_for_copy_paste():
    out = _run("""
const storage = new FakeStorage();
const journal = createVoiceDiagLog({ storage, now, consoleSink: silentConsole });
journal.record("otis", "Modèle Vosk prêt en 4.2 s");
const text = formatVoiceDiagEntries(journal.read());
journal.clear();
console.log(JSON.stringify({ text, after: journal.read() }));
""")
    assert out["text"] == "2026-11-04T08:00:00.000Z [otis] Modèle Vosk prêt en 4.2 s"
    assert out["after"] == []


# --- Câblage dans le pipeline vocal (aucun changement de comportement) ---

def _source(relative: str) -> str:
    return (STATIC / relative).read_text(encoding="utf-8")


def test_wake_word_detector_logs_into_the_journal():
    speech = _source("js/speech.js")
    assert 'from "./voice_diag_log.js"' in speech
    assert re.search(r'voiceDiagLog\.record\("otis"', speech)


def test_vosk_loading_reports_progress_worker_crash_and_a_stuck_audio_context():
    vosk = _source("js/wake_word_vosk.js")
    assert "toujours en chargement" in vosk
    assert 'client.worker.addEventListener("error"' in vosk
    assert "resume() toujours en attente" in vosk
    assert "getUserMedia" in vosk and "ms" in vosk


def test_dictation_logs_trigger_microphone_delay_and_stop_reason():
    speech = _source("js/speech.js")
    for reason in ('"silence"', '"inactivité"', '"bouton"', '"relâché"'):
        assert reason in speech, reason
    assert "ignoré (trop court)" in speech
    assert re.search(r'voiceDiagLog\.record\("dictée"', speech)


def test_audio_upload_logs_status_duration_and_queueing():
    chat = _source("js/views/chat_view.js")
    assert 'from "../voice_diag_log.js"' in chat
    assert re.search(r'voiceDiagLog\.record\("envoi"', chat)
    assert "mis en attente" in chat


def test_service_worker_caches_the_journal_module_in_a_new_version():
    sw = _source("sw.js")
    assert '"/static/js/voice_diag_log.js"' in sw
    version = int(re.search(r"pah-pwa-cache-v(\d+)", sw).group(1))
    assert version >= 29


def test_diag_page_reads_and_clears_the_app_journal():
    html = client.get("/static/audio_diag.html").text
    assert 'id="btn-app-journal"' in html
    assert 'id="btn-app-journal-clear"' in html
    assert "/static/js/voice_diag_log.js" in html


def test_diag_page_reports_environment_and_model_download_alone():
    html = client.get("/static/audio_diag.html").text
    assert "deviceMemory" in html
    assert "storage.estimate" in html
    assert "indexedDB.databases" in html
    assert 'data-mode="vosk-model-download"' in html
    assert "AudioContext créé sans geste" in html
