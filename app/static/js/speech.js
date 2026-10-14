// Module de Synthèse Vocale (TTS), Moteur VAD Anti-Coupure (MediaRecorder) et Ergonomie Vocale
import { state } from "./config.js";
import { audioFocusManager } from "./audio_focus.js";

export const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

let frenchVoices = [];
let mediaRecorder = null;
let audioChunks = [];
let audioStream = null;
let audioContext = null;
let analyserNode = null;
let animFrameId = null;
let silenceTimer = null;
let isSpeakingDetected = false;
let isRecording = false;
let legacyRecognition = null;
let undoTimeoutId = null;

// Gestion Audio Focus & Ducking
let activeUtterance = null;
let ttsWatchdogTimer = null;
let wakeRecInstance = null;
let wakeWordPaused = false;
let onWakeWordCallback = null;

// ============================================================================
// 1. Synthèse Vocale (TTS)
// ============================================================================

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
  }

  utterance.onstart = () => {
    pauseWakeWordDetector();
    audioFocusManager.requestDucking("tts");
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


// ============================================================================
// 2. Toast d'Annulation Tactile Immédiate (« Undo »)
// ============================================================================

export function showUndoToast(actionDescription, onUndoCallback) {
  const toast = document.getElementById("undo-toast");
  const textEl = document.getElementById("undo-toast-text");
  const btnUndo = document.getElementById("btn-undo-action");
  if (!toast || !btnUndo) return;

  if (undoTimeoutId) {
    clearTimeout(undoTimeoutId);
  }

  if (textEl) {
    textEl.textContent = actionDescription || "Dernière action réversible";
  }

  btnUndo.onclick = () => {
    hideUndoToast();
    if (onUndoCallback) onUndoCallback();
  };

  toast.style.display = "flex";
  toast.classList.add("visible");

  // Masquage automatique après 8 secondes
  undoTimeoutId = setTimeout(() => {
    hideUndoToast();
  }, 8000);
}

export function hideUndoToast() {
  const toast = document.getElementById("undo-toast");
  if (!toast) return;
  if (undoTimeoutId) {
    clearTimeout(undoTimeoutId);
    undoTimeoutId = null;
  }
  toast.classList.remove("visible");
  setTimeout(() => {
    toast.style.display = "none";
  }, 300);
}

// ============================================================================
// 3. Moteur VAD Anti-Coupure (MediaRecorder & Analyse Audio Fréquentielle)
// ============================================================================

export function initSpeechRecognition(onResultCallback, onNotAllowedCallback, onAudioBlobCallback) {
  const micWrapper = document.getElementById("mic-wrapper");
  const micBtn = document.getElementById("mic-btn");
  const voiceBarArea = document.getElementById("voice-bar-area");
  const interimTranscript = document.getElementById("interim-transcript");
  const visualBars = document.querySelectorAll(".visual-bar");

  // Détection du mimeType supporté pour MediaRecorder
  let preferredMime = "audio/webm;codecs=opus";
  if (!window.MediaRecorder || !MediaRecorder.isTypeSupported(preferredMime)) {
    preferredMime = MediaRecorder && MediaRecorder.isTypeSupported("audio/webm")
      ? "audio/webm"
      : (MediaRecorder && MediaRecorder.isTypeSupported("audio/mp4") ? "audio/mp4" : "");
  }

  const supportsMediaRecorder = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder && preferredMime);

  // Fallback Web Speech API classique si MediaRecorder indisponible
  if (!supportsMediaRecorder) {
    console.info("[STT] MediaRecorder non disponible, bascule sur Web Speech API");
    return initLegacyWebSpeech(onResultCallback, onNotAllowedCallback);
  }

  async function startAudioCapture() {
    try {
      pauseWakeWordDetector();
      audioFocusManager.requestDucking("recording");
      audioChunks = [];
      isSpeakingDetected = false;

      audioStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      mediaRecorder = new MediaRecorder(audioStream, { mimeType: preferredMime });

      mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          audioChunks.push(e.data);
        }
      };

      mediaRecorder.onstop = () => {
        cleanupAudioNodes();
        const blob = new Blob(audioChunks, { type: preferredMime });
        if (blob.size > 1000 && onAudioBlobCallback) {
          onAudioBlobCallback(blob);
        } else if (audioChunks.length > 0 && onResultCallback) {
          // Rien d'audible
          console.debug("[STT] Enregistrement trop court ou vide.");
        }
      };

      mediaRecorder.start(250);
      isRecording = true;

      if (micWrapper) micWrapper.classList.add("recording");
      if (voiceBarArea) voiceBarArea.classList.add("active");
      if (interimTranscript) {
        interimTranscript.textContent = state.pushToTalk
          ? "Parlez en maintenant appuyé..."
          : "Je vous écoute (hésitations tolérées)...";
      }

      // Initialisation du VAD via Web Audio API si mode automatique
      setupVoiceActivityDetection();

    } catch (err) {
      console.warn("[VAD] Erreur accès microphone:", err);
      stopAudioCapture();
      if (onNotAllowedCallback) onNotAllowedCallback();
    }
  }

  function stopAudioCapture() {
    if (!isRecording) return;
    isRecording = false;

    if (silenceTimer) {
      clearTimeout(silenceTimer);
      silenceTimer = null;
    }

    if (micWrapper) micWrapper.classList.remove("recording");
    if (voiceBarArea) voiceBarArea.classList.remove("active");
    if (interimTranscript) interimTranscript.textContent = "Analyse en cours...";

    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      try {
        mediaRecorder.stop();
      } catch (e) {
        console.warn("Erreur stop mediaRecorder:", e);
      }
    }

    cleanupAudioNodes();
    audioFocusManager.releaseDucking("recording");
    resumeWakeWordDetector();
  }

  function cleanupAudioNodes() {
    if (animFrameId) {
      cancelAnimationFrame(animFrameId);
      animFrameId = null;
    }
    if (audioStream) {
      try {
        audioStream.getTracks().forEach((track) => track.stop());
      } catch (e) {}
      audioStream = null;
    }
    if (audioContext && audioContext.state !== "closed") {
      try {
        audioContext.close();
      } catch (e) {}
      audioContext = null;
    }
    analyserNode = null;
  }

  function setupVoiceActivityDetection() {
    if (state.pushToTalk) return; // Pas de VAD en mode Push-to-Talk explicite

    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;

    audioContext = new AudioContextClass();
    const source = audioContext.createMediaStreamSource(audioStream);
    analyserNode = audioContext.createAnalyser();
    analyserNode.fftSize = 256;
    analyserNode.smoothingTimeConstant = 0.4;
    source.connect(analyserNode);

    const bufferLength = analyserNode.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const SPEECH_THRESHOLD = 18; // Seuil de volume sonore (bruit ambiant vs voix)
    const silenceTimeoutMs = state.vadSilenceMs || 2000; // 2.0s de silence par défaut

    function checkAudioLevel() {
      if (!isRecording) return;

      analyserNode.getByteFrequencyData(dataArray);
      let sum = 0;
      for (let i = 0; i < bufferLength; i++) {
        sum += dataArray[i];
      }
      const avgLevel = sum / bufferLength;

      // Animation dynamique des barres proportionnelle à la voix
      if (visualBars && visualBars.length > 0) {
        const scale = Math.max(0.3, Math.min(2.0, avgLevel / 20));
        visualBars.forEach((bar) => {
          bar.style.transform = `scaleY(${scale})`;
        });
      }

      if (avgLevel > SPEECH_THRESHOLD) {
        // La personne parle ou reprend la parole
        isSpeakingDetected = true;
        if (silenceTimer) {
          clearTimeout(silenceTimer);
          silenceTimer = null;
        }
      } else if (isSpeakingDetected) {
        // La personne a parlé et marque une pause / hésitation
        if (!silenceTimer) {
          silenceTimer = setTimeout(() => {
            console.debug(`[VAD] Silence toléré de ${silenceTimeoutMs}ms atteint. Expédition de l'audio.`);
            stopAudioCapture();
          }, silenceTimeoutMs);
        }
      }

      animFrameId = requestAnimationFrame(checkAudioLevel);
    }

    checkAudioLevel();
  }

  // Branchement des écouteurs d'événements
  if (micBtn) {
    if (state.pushToTalk) {
      // Mode Push-to-Talk (maintenir pour parler)
      micBtn.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        startAudioCapture();
      });
      window.addEventListener("pointerup", () => {
        if (isRecording) stopAudioCapture();
      });
      window.addEventListener("pointercancel", () => {
        if (isRecording) stopAudioCapture();
      });
    } else {
      // Mode bascule VAD automatique
      micBtn.addEventListener("click", () => {
        if (isRecording) {
          stopAudioCapture();
        } else {
          startAudioCapture();
        }
      });
    }
  }

  // Wake Word discret in-app ("Otis") si activé
  if (state.wakeWordEnabled && SpeechRecognition) {
    startWakeWordDetection(() => {
      if (!isRecording) {
        console.debug("[WakeWord] Déclenchement automatique via mot-clé Otis !");
        startAudioCapture();
      }
    });
  }
}

// ============================================================================
// 4. Détecteur de Réveil In-App (« Otis ») Non-Intrusif & Contrôlable
// ============================================================================

export function setWakeWordEnabled(enabled) {
  state.wakeWordEnabled = !!enabled;
  if (state.wakeWordEnabled) {
    startWakeWordDetection();
  } else {
    stopWakeWordDetection();
  }
}

export function pauseWakeWordDetector() {
  wakeWordPaused = true;
  if (wakeRecInstance) {
    try {
      wakeRecInstance.abort();
    } catch (e) {}
  }
}

export function resumeWakeWordDetector() {
  wakeWordPaused = false;
  if (state.wakeWordEnabled && !isRecording && !audioFocusManager.isDucking()) {
    startWakeWordDetection();
  }
}

export function stopWakeWordDetection() {
  wakeWordPaused = false;
  if (wakeRecInstance) {
    try {
      wakeRecInstance.abort();
    } catch (e) {}
    wakeRecInstance = null;
  }
}

export function startWakeWordDetection(onWakeCallback = null) {
  if (onWakeCallback) {
    onWakeWordCallback = onWakeCallback;
  }
  if (!state.wakeWordEnabled || !SpeechRecognition) return;
  if (wakeWordPaused || isRecording || (typeof document !== "undefined" && document.hidden)) {
    return;
  }

  try {
    if (wakeRecInstance) {
      try { wakeRecInstance.abort(); } catch (e) {}
    }

    wakeRecInstance = new SpeechRecognition();
    wakeRecInstance.lang = "fr-FR";
    wakeRecInstance.continuous = true;
    wakeRecInstance.interimResults = true;

    wakeRecInstance.onresult = (evt) => {
      for (let i = evt.resultIndex; i < evt.results.length; ++i) {
        const transcript = evt.results[i][0].transcript.toLowerCase();
        if (transcript.includes("otis") || transcript.includes("dis otis")) {
          if (onWakeWordCallback) onWakeWordCallback();
          break;
        }
      }
    };

    wakeRecInstance.onerror = (e) => {
      console.debug("[WakeWord] Événement d'écoute:", e?.error || e);
    };

    wakeRecInstance.onend = () => {
      // Reconnexion uniquement si l'état est toujours actif et non en pause
      if (
        state.wakeWordEnabled &&
        !wakeWordPaused &&
        !isRecording &&
        !audioFocusManager.isDucking() &&
        (typeof document === "undefined" || !document.hidden)
      ) {
        setTimeout(() => {
          try {
            if (wakeRecInstance) wakeRecInstance.start();
          } catch (e) {}
        }, 500);
      }
    };

    wakeRecInstance.start();
  } catch (e) {
    console.warn("Wake word non initialisé:", e);
  }
}

// Surveillance de la visibilité de l'application
if (typeof document !== "undefined") {
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      pauseWakeWordDetector();
    } else {
      resumeWakeWordDetector();
    }
  });
}


// Fallback legacy Web Speech API si MediaRecorder indisponible
function initLegacyWebSpeech(onResultCallback, onNotAllowedCallback) {
  const micWrapper = document.getElementById("mic-wrapper");
  const micBtn = document.getElementById("mic-btn");
  const voiceBarArea = document.getElementById("voice-bar-area");
  const interimTranscript = document.getElementById("interim-transcript");

  legacyRecognition = new SpeechRecognition();
  legacyRecognition.lang = "fr-FR";
  legacyRecognition.interimResults = true;
  legacyRecognition.continuous = false;

  legacyRecognition.onstart = () => {
    if (micWrapper) micWrapper.classList.add("recording");
    if (voiceBarArea) voiceBarArea.classList.add("active");
    if (interimTranscript) interimTranscript.textContent = "Je vous écoute...";
  };

  legacyRecognition.onresult = (event) => {
    let finalTranscript = "";
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; ++i) {
      if (event.results[i].isFinal) {
        finalTranscript += event.results[i][0].transcript;
      } else {
        interim += event.results[i][0].transcript;
      }
    }
    if (interimTranscript) interimTranscript.textContent = interim || finalTranscript;
    if (finalTranscript.trim() && onResultCallback) {
      onResultCallback(finalTranscript.trim());
    }
  };

  legacyRecognition.onerror = (e) => {
    if (micWrapper) micWrapper.classList.remove("recording");
    if (voiceBarArea) voiceBarArea.classList.remove("active");
    if (e.error === "not-allowed" && onNotAllowedCallback) onNotAllowedCallback();
  };

  legacyRecognition.onend = () => {
    if (micWrapper) micWrapper.classList.remove("recording");
    if (voiceBarArea) voiceBarArea.classList.remove("active");
  };

  if (micBtn) {
    micBtn.addEventListener("click", () => {
      try { legacyRecognition.start(); } catch (e) {}
    });
  }
}
