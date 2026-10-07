// Module de Synthèse Vocale (TTS) et Reconnaissance Vocale (STT / Web Speech)
import { state } from "./config.js";

export const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

let frenchVoices = [];
let recognition = null;
let isRecording = false;

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

  // Trier les voix : naturelles / Google / premium d'abord
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

export function speak(text, overrideVoiceUri = null) {
  if (!state.ttsEnabled || !("speechSynthesis" in window) || !text) return;
  window.speechSynthesis.cancel();
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
  window.speechSynthesis.speak(utterance);
}

export function initSpeechRecognition(onResultCallback, onNotAllowedCallback) {
  const micWrapper = document.getElementById("mic-wrapper");
  const micBtn = document.getElementById("mic-btn");
  const voiceBarArea = document.getElementById("voice-bar-area");
  const interimTranscript = document.getElementById("interim-transcript");

  if (!SpeechRecognition) {
    if (micBtn) {
      micBtn.addEventListener("click", () => {
        alert("La reconnaissance vocale n'est pas supportée par votre navigateur actuel. Vous pouvez saisir votre message au clavier.");
      });
    }
    return;
  }

  recognition = new SpeechRecognition();
  recognition.lang = "fr-FR";
  recognition.interimResults = true;
  recognition.continuous = false;

  recognition.onstart = () => {
    isRecording = true;
    if (micWrapper) micWrapper.classList.add("recording");
    if (voiceBarArea) voiceBarArea.classList.add("active");
    if (interimTranscript) interimTranscript.textContent = "Je vous écoute...";
  };

  recognition.onresult = (event) => {
    let finalTranscript = "";
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; ++i) {
      if (event.results[i].isFinal) {
        finalTranscript += event.results[i][0].transcript;
      } else {
        interim += event.results[i][0].transcript;
      }
    }
    if (interimTranscript) interimTranscript.textContent = interim || finalTranscript || "Je vous écoute...";
    if (finalTranscript.trim() && onResultCallback) {
      onResultCallback(finalTranscript.trim());
    }
  };

  recognition.onerror = (event) => {
    console.warn("[STT Error]", event.error);
    stopRecording();
    if (event.error === "not-allowed" && onNotAllowedCallback) {
      onNotAllowedCallback();
    }
  };

  recognition.onend = () => {
    stopRecording();
  };

  function startRecording() {
    try {
      recognition.start();
    } catch (e) {
      console.warn("Recognition start:", e);
    }
  }

  function stopRecording() {
    isRecording = false;
    if (micWrapper) micWrapper.classList.remove("recording");
    if (voiceBarArea) voiceBarArea.classList.remove("active");
    if (interimTranscript) interimTranscript.textContent = "";
  }

  if (micBtn) {
    micBtn.addEventListener("click", () => {
      if (isRecording) {
        if (recognition) recognition.stop();
        stopRecording();
      } else {
        startRecording();
      }
    });
  }
}
