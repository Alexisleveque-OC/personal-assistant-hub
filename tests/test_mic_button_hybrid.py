"""Bouton micro hybride (décision utilisateur du 04/11) : en mode « maintenir », un appui long parle tant qu'il est
maintenu, un appui bref bascule (arrêt au tap suivant ou au silence). Bug corrigé (journal du 04/11) : tap puis tap
lançait une capture fantôme jamais arrêtée et jetait sans message un 2e enregistrement vide."""
import re
from pathlib import Path

from tests.test_wake_word_vosk import NODE  # même Node que les autres tests JS

import pytest
import subprocess

SPEECH = Path(__file__).resolve().parent.parent / "app" / "static" / "js" / "speech.js"


def _speech() -> str:
    return SPEECH.read_text(encoding="utf-8")


def _function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    depth, i = 0, source.index("{", start)
    for j in range(i, len(source)):
        depth += {"{": 1, "}": -1}.get(source[j], 0)
        if depth == 0:
            return source[i:j + 1]
    raise AssertionError(signature)


def test_short_press_is_a_tap_and_long_press_is_a_hold():
    if not NODE:
        pytest.skip("Node.js indisponible")
    source = _speech()
    threshold_line = re.search(r"export const HOLD_THRESHOLD_MS = \d+;", source).group(0)
    body = _function_body(source, "export function isHoldRelease(heldMs)")
    code = (
        f"{threshold_line}\nfunction isHoldRelease(heldMs) {body}\n"
        "console.log(JSON.stringify([isHoldRelease(120), isHoldRelease(399), isHoldRelease(400), isHoldRelease(2500)]));"
    )
    result = subprocess.run([NODE, "--input-type=module"], input=code, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[false,false,true,true]"


def test_a_capture_already_starting_or_running_is_never_started_twice():
    body = _function_body(_speech(), "async function startAudioCapture(")
    assert re.search(r"if \(isRecording \|\| isStartingCapture\)", body)
    assert "isStartingCapture = true" in body
    assert "isStartingCapture = false" in body


def test_a_stop_requested_while_the_microphone_opens_is_applied_once_open():
    source = _speech()
    stop = _function_body(source, "function stopAudioCapture(")
    assert "pendingStopReason = reason" in stop
    start = _function_body(source, "async function startAudioCapture(")
    assert "pendingStopReason" in start


def test_push_to_talk_press_stops_a_running_capture_and_release_only_stops_a_hold():
    behavior = _function_body(_speech(), "export function setupMicButtonBehavior(")
    assert re.search(r"if \(isRecording \|\| isStartingCapture\)\s*\{[^}]*activeStopAudioCapture\(\"bouton\"\)", behavior)
    assert "isHoldRelease(" in behavior
    assert 'activeStopAudioCapture("relâché")' in behavior


def test_window_release_listeners_are_replaced_not_accumulated():
    behavior = _function_body(_speech(), "export function setupMicButtonBehavior(")
    assert 'window.removeEventListener("pointerup", windowReleaseHandler)' in behavior
    assert 'window.removeEventListener("pointercancel", windowReleaseHandler)' in behavior


def test_silence_never_cuts_a_held_press_and_vad_runs_for_taps():
    source = _speech()
    vad = _function_body(source, "function setupVoiceActivityDetection(")
    assert vad.count("if (pointerHeld)") >= 2
    start = _function_body(source, "async function startAudioCapture(")
    assert "setupVoiceActivityDetection(true)" in start


def test_too_short_recording_is_announced_to_the_user():
    source = _speech()
    assert "Message trop court : rien n'a été envoyé." in source
