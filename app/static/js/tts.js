// Synthèse vocale (TTS) : voix françaises, lecture des réponses d'Otis avec baisse du son (audio focus)
// et pause du mot-clé « Otis » pendant la lecture.
import { state } from "./config.js";
import { audioFocusManager } from "./audio_focus.js";
import { pauseWakeWordDetector, resumeWakeWordDetector } from "./wake_word.js";

let frenchVoices = [];
// Référence globale : évite le ramasse-miettes prématuré de l'énoncé dans Chrome Mobile.
let activeUtterance = null;
let ttsWatchdogTimer = null;

export function populateVoiceList(voiceSelect) {
  if (!("speechSynthesis" in window) || !voiceSelect) return;
  const allVoices = window.speechSynthesis.getVoices();
  frenchVoices = allVoices.filter((v) => v.lang.startsWith("fr"));

  voiceSelect.innerHTML = "";
  if (frenchVoices.length === 0) {
    const opt = document.createElement("option");
    opt.textContent = "Voix française par défaut du système";
    opt.value = "";
    voiceSelect.appendChild(opt);
    return;
  }

  frenchVoices.sort((a, b) => {
    const aScore = (a.name.includes("Google") || a.name.includes("Natural")) ? 1 : 0;
    const bScore = (b.name.includes("Google") || b.name.includes("Natural")) ? 1 : 0;
    return bScore - aScore;
  });

  let matched = false;
  frenchVoices.forEach((voice) => {
    const option = document.createElement("option");
    option.value = voice.voiceURI;
    option.textContent = `${voice.name} (${voice.lang})`;
    if (voice.voiceURI === state.selectedVoiceUri) {
      option.selected = true;
      matched = true;
    }
    voiceSelect.appendChild(option);
  });

  if (!matched && frenchVoices.length > 0) {
    voiceSelect.selectedIndex = 0;
    state.selectedVoiceUri = frenchVoices[0].voiceURI;
  }
}

// Annonce aux vues (bouton pause) qu'Otis commence ou arrête de parler.
function announceSpeaking(speaking) {
  if (typeof window !== "undefined" && typeof window.dispatchEvent === "function") {
    window.dispatchEvent(new CustomEvent("tts-state", { detail: { speaking } }));
  }
}

export function cancelSpeaking() {
  if (typeof window !== "undefined" && "speechSynthesis" in window) {
    try {
      window.speechSynthesis.cancel();
    } catch (e) {}
  }
  if (ttsWatchdogTimer) {
    clearTimeout(ttsWatchdogTimer);
    ttsWatchdogTimer = null;
  }
  activeUtterance = null;
  audioFocusManager.releaseDucking("tts");
  resumeWakeWordDetector();
  announceSpeaking(false);
}

export function speak(text, overrideVoiceUri = null) {
  if (!state.ttsEnabled || !("speechSynthesis" in window) || !text) return;
  cancelSpeaking();

  const cleanText = text.replace(/[*_#]/g, "");
  const utterance = new SpeechSynthesisUtterance(cleanText);
  utterance.lang = "fr-FR";
  utterance.rate = 1.02;
  utterance.pitch = 1.0;

  const uriToUse = overrideVoiceUri || state.selectedVoiceUri;
  if (uriToUse && frenchVoices.length > 0) {
    const foundVoice = frenchVoices.find((v) => v.voiceURI === uriToUse);
    if (foundVoice) utterance.voice = foundVoice;
  }

  function handleTtsDone() {
    if (ttsWatchdogTimer) {
      clearTimeout(ttsWatchdogTimer);
      ttsWatchdogTimer = null;
    }
    activeUtterance = null;
    audioFocusManager.releaseDucking("tts");
    resumeWakeWordDetector();
    announceSpeaking(false);
  }

  utterance.onstart = () => {
    pauseWakeWordDetector();
    audioFocusManager.requestDucking("tts");
    announceSpeaking(true);
  };

  utterance.onend = () => {
    handleTtsDone();
  };

  utterance.onerror = (e) => {
    console.debug("[TTS] Fin ou interruption de lecture vocale:", e);
    handleTtsDone();
  };

  // Référence globale activeUtterance pour éviter le garbage collection prématuré dans Chrome Mobile
  activeUtterance = utterance;

  // Watchdog de sécurité (durée estimée + marge)
  const watchdogMs = Math.max(3000, cleanText.length * 150 + 3000);
  ttsWatchdogTimer = setTimeout(() => {
    console.debug("[TTS] Watchdog audio focus déclenché");
    handleTtsDone();
  }, watchdogMs);

  audioFocusManager.requestDucking("tts");
  window.speechSynthesis.speak(utterance);
}
