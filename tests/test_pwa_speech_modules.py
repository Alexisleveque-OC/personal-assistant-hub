"""Refacto anti-tokens, lot 2 : speech.js est découpé en modules par responsabilité
(synthèse vocale, capture micro + VAD, mot-clé « Otis », barre « Annuler »)."""
import re
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parent.parent / "app" / "static" / "js"
STATIC = JS.parent

MODULES = {
    "tts.js": ["populateVoiceList", "cancelSpeaking", "speak"],
    "mic_capture.js": [
        "SpeechRecognition", "HOLD_THRESHOLD_MS", "isHoldRelease", "captureOnce", "stopCapture",
        "initSpeechRecognition", "setupMicButtonBehavior", "defaultWakeTrigger",
    ],
    "wake_word.js": [
        "DEFAULT_WAKE_VARIANTS", "isWakeWordMatch", "extractCommandAfterWakeWord", "playWakeChime",
        "triggerWakeCapture", "updateWakeWordIndicator", "setWakeWordEnabled", "pauseWakeWordDetector",
        "resumeWakeWordDetector", "stopWakeWordDetection", "startWakeWordDetection", "registerWakeCapture",
    ],
    "undo_bar.js": ["showUndoToast", "hideUndoToast"],
}


@pytest.mark.parametrize("module,exports", MODULES.items())
def test_each_module_exports_its_responsibility(module, exports):
    source = (JS / module).read_text(encoding="utf-8")
    for name in exports:
        assert re.search(rf"export (async )?(function|const|let) {name}\b", source), f"{name} dans {module}"
    assert len(source.splitlines()) < 500, f"{module} trop long"


def test_wake_word_is_the_lower_layer_without_import_cycle():
    wake = (JS / "wake_word.js").read_text(encoding="utf-8")
    assert "./mic_capture.js" not in wake and "./tts.js" not in wake
