// Module de Synthèse Vocale (TTS), Moteur VAD Anti-Coupure (MediaRecorder) et Ergonomie Vocale
import { state } from "./config.js";
import { audioFocusManager } from "./audio_focus.js";
import { VoskWakeWordDetector } from "./wake_word_vosk.js";
import { showToastError, showToastInfo } from "./toast.js";
import { voiceDiagLog } from "./voice_diag_log.js";

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

// Callbacks globaux et états Audio/Wake-Word
let savedOnResultCallback = null;
let savedOnNotAllowedCallback = null;
let savedOnAudioBlobCallback = null;
let activeStartAudioCapture = null;
let activeStopAudioCapture = null;
let initialInactivityTimer = null;
// Diagnostic de la dictée (journal du micro) : début d'enregistrement et niveau VAD maximal atteint.
let recordingStartedAt = 0;
let peakVadLevel = null;

// Bouton hybride (mode « maintenir », décision du 04/11) : appui long = parle tant que maintenu,
// appui bref = bascule (arrêt au tap suivant ou au silence).
export const HOLD_THRESHOLD_MS = 400;
let isStartingCapture = false; // micro en cours d'ouverture : empêche une 2e capture fantôme
let pendingStopReason = null; // arrêt demandé avant que le micro soit ouvert
let pointerHeld = false; // le silence ne coupe jamais un appui maintenu
let pressStartedAt = 0;
let windowReleaseHandler = null;

export function isHoldRelease(heldMs) {
  return heldMs >= HOLD_THRESHOLD_MS;
}

// Gestion Audio Focus & Ducking
let activeUtterance = null;
let ttsWatchdogTimer = null;
let voskDetector = null;
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

// État « écoute » du micro : `.is-listening` sur le bouton (hub.css), `.recording` sur son conteneur.
// Relu à chaque fois : le bouton est remplacé par setupMicButtonBehavior() et la barre de saisie change de feuille.
function setMicListening(listening) {
  const wrapper = document.getElementById("mic-wrapper");
  const button = document.getElementById("mic-btn");
  if (wrapper) wrapper.classList.toggle("recording", listening);
  if (button) button.classList.toggle("is-listening", listening);
}

export function initSpeechRecognition(onResultCallback, onNotAllowedCallback, onAudioBlobCallback) {
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

  async function startAudioCapture(isWakeTriggered = false) {
    const trigger = isWakeTriggered ? "mot-clé" : (state.pushToTalk ? "maintien" : "bouton");
    if (isRecording || isStartingCapture) {
      voiceDiagLog.record("dictée", `Démarrage ignoré (déclencheur : ${trigger}) : une capture est déjà en cours`);
      return;
    }
    isStartingCapture = true;
    pendingStopReason = null;
    voiceDiagLog.record("dictée", `Démarrage (déclencheur : ${trigger})`);
    try {
      pauseWakeWordDetector();
      audioFocusManager.requestDucking("recording");
      audioChunks = [];
      isSpeakingDetected = false;

      // Délai court de libération du micro si transition depuis la détection du mot-clé
      if (isWakeTriggered) {
        await new Promise((resolve) => setTimeout(resolve, 80));
      }

      const micRequestedAt = performance.now();
      audioStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      voiceDiagLog.record("dictée", `Micro ouvert en ${Math.round(performance.now() - micRequestedAt)} ms (${preferredMime})`);

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
          voiceDiagLog.record("dictée", `Enregistrement de ${(blob.size / 1024).toFixed(1)} Ko transmis pour transcription`);
          onAudioBlobCallback(blob);
        } else if (audioChunks.length > 0 && onResultCallback) {
          // Rien d'audible
          console.debug("[STT] Enregistrement trop court ou vide.");
        }
        if (blob.size <= 1000) {
          voiceDiagLog.record("dictée", `Enregistrement de ${blob.size} octets ignoré (trop court), rien n'est envoyé`);
          showToastInfo("Message trop court : rien n'a été envoyé.", "Micro");
        }
      };

      mediaRecorder.start(250);
      isRecording = true;
      isStartingCapture = false;
      recordingStartedAt = performance.now();
      peakVadLevel = null;

      setMicListening(true);
      if (voiceBarArea) voiceBarArea.classList.add("active");
      if (interimTranscript) {
        interimTranscript.textContent = (state.pushToTalk && !isWakeTriggered)
          ? "Je vous écoute (relâchez, ou touchez à nouveau pour envoyer)..."
          : "Je vous écoute (hésitations tolérées)...";
      }

      // VAD dans tous les modes : un appui bref (bascule) doit pouvoir s'arrêter au silence ;
      // un appui maintenu n'est jamais coupé par le silence (voir pointerHeld).
      setupVoiceActivityDetection(true);

      // Relâché ou retouché pendant l'ouverture du micro : l'arrêt demandé s'applique maintenant.
      if (pendingStopReason) {
        const reason = pendingStopReason;
        pendingStopReason = null;
        stopAudioCapture(reason);
      }

    } catch (err) {
      console.warn("[VAD] Erreur accès microphone:", err);
      voiceDiagLog.record("dictée", `Ouverture du micro impossible : ${err.name || ""} ${err.message}`);
      isStartingCapture = false;
      pendingStopReason = null;
      stopAudioCapture("erreur");
      if (onNotAllowedCallback) onNotAllowedCallback();
    }
  }

  // reason : silence, inactivité, bouton, relâché ou erreur (journal du micro).
  function stopAudioCapture(reason = "inconnue") {
    if (!isRecording) {
      if (isStartingCapture) {
        pendingStopReason = reason;
        voiceDiagLog.record("dictée", `Arrêt (${reason}) demandé pendant l'ouverture du micro : appliqué dès l'ouverture`);
      }
      return;
    }
    isRecording = false;
    const level = peakVadLevel === null
      ? "VAD inactive"
      : `parole détectée : ${isSpeakingDetected ? "oui" : "non"}, niveau max ${peakVadLevel.toFixed(0)} / seuil 18`;
    voiceDiagLog.record(
      "dictée",
      `Arrêt (${reason}) après ${((performance.now() - recordingStartedAt) / 1000).toFixed(1)} s, ${level}`
    );

    if (silenceTimer) {
      clearTimeout(silenceTimer);
      silenceTimer = null;
    }
    if (initialInactivityTimer) {
      clearTimeout(initialInactivityTimer);
      initialInactivityTimer = null;
    }

    setMicListening(false);
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

  function setupVoiceActivityDetection(forceVad = false) {
    if (state.pushToTalk && !forceVad) return; // Pas de VAD en mode Push-to-Talk explicite

    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;

    audioContext = new AudioContextClass();
    if (audioContext.state === "suspended") {
      audioContext.resume().catch((e) => console.debug("AudioContext resume:", e));
    }
    const source = audioContext.createMediaStreamSource(audioStream);
    analyserNode = audioContext.createAnalyser();
    analyserNode.fftSize = 256;
    analyserNode.smoothingTimeConstant = 0.4;
    source.connect(analyserNode);

    const bufferLength = analyserNode.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const SPEECH_THRESHOLD = 18; // Seuil de volume sonore (bruit ambiant vs voix)
    const silenceTimeoutMs = state.vadSilenceMs || 2000; // 2.0s de silence par défaut

    // Watchdog d'inactivité initiale : si aucune voix n'est détectée sous 7 secondes après réveil
    if (initialInactivityTimer) clearTimeout(initialInactivityTimer);
    initialInactivityTimer = setTimeout(() => {
      if (pointerHeld) return;
      if (!isSpeakingDetected && isRecording) {
        console.debug("[VAD] Inactivité prolongée après réveil vocal. Arrêt.");
        stopAudioCapture("inactivité");
      }
    }, 7000);

    function checkAudioLevel() {
      if (!isRecording) return;

      analyserNode.getByteFrequencyData(dataArray);
      let sum = 0;
      for (let i = 0; i < bufferLength; i++) {
        sum += dataArray[i];
      }
      const avgLevel = sum / bufferLength;
      peakVadLevel = Math.max(peakVadLevel ?? 0, avgLevel);

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
        if (initialInactivityTimer) {
          clearTimeout(initialInactivityTimer);
          initialInactivityTimer = null;
        }
        if (silenceTimer) {
          clearTimeout(silenceTimer);
          silenceTimer = null;
        }
      } else if (isSpeakingDetected) {
        // La personne a parlé et marque une pause / hésitation
        if (!silenceTimer) {
          silenceTimer = setTimeout(() => {
            if (pointerHeld) {
              silenceTimer = null; // réarmé à la prochaine pause une fois le bouton relâché
              return;
            }
            console.debug(`[VAD] Silence toléré de ${silenceTimeoutMs}ms atteint. Expédition de l'audio.`);
            stopAudioCapture("silence");
          }, silenceTimeoutMs);
        }
      }

      animFrameId = requestAnimationFrame(checkAudioLevel);
    }

    checkAudioLevel();
  }

  savedOnResultCallback = onResultCallback;
  savedOnNotAllowedCallback = onNotAllowedCallback;
  savedOnAudioBlobCallback = onAudioBlobCallback;

  activeStartAudioCapture = startAudioCapture;
  activeStopAudioCapture = stopAudioCapture;
  setupMicButtonBehavior();

  // Enregistrement permanent du handler de réveil par défaut
  onWakeWordCallback = (transcript) => defaultWakeTrigger(transcript);

  // Wake Word discret in-app ("Otis") si activé
  if (state.wakeWordEnabled) {
    startWakeWordDetection(onWakeWordCallback);
  }
}

export function setupMicButtonBehavior() {
  const micBtn = document.getElementById("mic-btn");
  const interimTranscript = document.getElementById("interim-transcript");
  if (!micBtn || !activeStartAudioCapture || !activeStopAudioCapture) return;

  // Remplacement propre du nœud pour purger d'anciens écouteurs
  const newMicBtn = micBtn.cloneNode(true);
  micBtn.parentNode.replaceChild(newMicBtn, micBtn);

  // Les écouteurs globaux de relâchement sont remplacés à chaque appel (sinon ils s'accumulent à chaque
  // enregistrement des réglages et un relâchement arrêterait une capture lancée en mode bascule).
  if (windowReleaseHandler) {
    window.removeEventListener("pointerup", windowReleaseHandler);
    window.removeEventListener("pointercancel", windowReleaseHandler);
    windowReleaseHandler = null;
  }
  pointerHeld = false;

  if (state.pushToTalk) {
    if (interimTranscript) interimTranscript.textContent = "Maintenez pour parler, ou touchez pour démarrer / arrêter...";
    newMicBtn.title = "Maintenir pour parler, ou toucher pour démarrer puis arrêter";

    // Gestion pointeur (souris PC + tactile mobile)
    newMicBtn.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      // Capture en cours (bascule après un appui bref, ou micro en cours d'ouverture) : ce toucher l'arrête.
      if (isRecording || isStartingCapture) {
        activeStopAudioCapture("bouton");
        return;
      }
      try {
        newMicBtn.setPointerCapture(e.pointerId);
      } catch (err) {}
      pointerHeld = true;
      pressStartedAt = performance.now();
      activeStartAudioCapture(false);
    });

    windowReleaseHandler = (e) => {
      try {
        if (newMicBtn.hasPointerCapture && newMicBtn.hasPointerCapture(e.pointerId)) {
          newMicBtn.releasePointerCapture(e.pointerId);
        }
      } catch (err) {}
      if (!pointerHeld) return;
      pointerHeld = false;
      const heldMs = Math.round(performance.now() - pressStartedAt);
      if (isHoldRelease(heldMs)) {
        activeStopAudioCapture("relâché");
      } else {
        voiceDiagLog.record("dictée", `Appui bref (${heldMs} ms) : bascule, arrêt au prochain toucher ou au silence`);
      }
    };
    window.addEventListener("pointerup", windowReleaseHandler);
    window.addEventListener("pointercancel", windowReleaseHandler);
  } else {
    // Mode bascule VAD automatique (1 clic pour démarrer, 1 clic ou silence pour arrêter)
    if (interimTranscript) interimTranscript.textContent = "Cliquez sur le micro pour parler...";
    newMicBtn.title = "Cliquer pour parler (Anti-coupure automatique)";

    newMicBtn.addEventListener("click", () => {
      if (isRecording) {
        activeStopAudioCapture("bouton");
      } else {
        activeStartAudioCapture(false);
      }
    });
  }
}

// ============================================================================
// 4. Détecteur de Réveil In-App (« Otis ») Non-Intrusif & Calibrage Guidé
// ============================================================================

export const DEFAULT_WAKE_VARIANTS = [
  "otis",
  "dis otis",
  "dit otis",
  "hey otis",
  "salut otis",
  "ok otis",
  "autiste",
  "dis autiste",
  "dit autiste",
  "notice",
  "la notice",
  "au tisse",
  "oh tisse",
  "aux tisse",
  "hautisse",
  "hotis",
  "hostis",
  "hosties",
  "nautis",
  "rotis",
  "rôti"
];

export function isWakeWordMatch(transcript) {
  if (!transcript) return false;
  const clean = transcript.toLowerCase().trim();
  const allVariants = [
    ...DEFAULT_WAKE_VARIANTS,
    ...(state.wakeWordCustomVariants || [])
  ];
  return allVariants.some((variant) => clean.includes(variant));
}

export function extractCommandAfterWakeWord(transcript) {
  if (!transcript) return "";
  const clean = transcript.trim();
  const allVariants = [
    ...DEFAULT_WAKE_VARIANTS,
    ...(state.wakeWordCustomVariants || [])
  ];
  for (const variant of allVariants) {
    const escaped = variant.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const regex = new RegExp(`^.*?\\b${escaped}\\b[\\s,.:;!-]*`, "i");
    if (regex.test(clean)) {
      return clean.replace(regex, "").trim();
    }
  }
  return "";
}

export function playWakeChime() {
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    const ctx = new AudioContextClass();
    if (ctx.state === "suspended") {
      ctx.resume().catch(() => {});
    }
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    // Bi-ton élégant : 587.33Hz (Ré5) montant à 880Hz (La5) en 80ms
    osc.frequency.setValueAtTime(587.33, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.08);
    gain.gain.setValueAtTime(0.12, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.22);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.22);
    setTimeout(() => {
      try { ctx.close(); } catch (e) {}
    }, 350);
  } catch (e) {
    console.debug("[Audio] Chime non joué:", e);
  }
}

export function defaultWakeTrigger(detectedTranscript = "") {
  if (isRecording) return;
  const trailingCommand = extractCommandAfterWakeWord(detectedTranscript);
  if (trailingCommand && trailingCommand.length > 2 && savedOnResultCallback) {
    console.debug("[WakeWord] Commande enchaînée détectée immédiatement:", trailingCommand);
    pauseWakeWordDetector();
    savedOnResultCallback(trailingCommand);
  } else if (activeStartAudioCapture) {
    console.debug("[WakeWord] Déclenchement automatique de la capture audio !");
    activeStartAudioCapture(true);
  }
}

export function triggerWakeCapture(detectedTranscript = "") {
  if (onWakeWordCallback) {
    onWakeWordCallback(detectedTranscript);
  } else {
    defaultWakeTrigger(detectedTranscript);
  }
}

export function updateWakeWordIndicator(statusOverride = null) {
  const indicator = document.getElementById("wake-word-indicator");
  if (!indicator) return;

  indicator.style.display = "inline-flex";
  const label = indicator.querySelector(".wake-label");

  if (!state.wakeWordEnabled) {
    indicator.className = "wake-word-indicator disabled";
    indicator.title = "Mode Micro au clic (musique protégée). Cliquez pour activer le mot-clé mains-libres 'Otis'.";
    if (label) label.textContent = "Micro au clic";
    return;
  }

  if (statusOverride === "triggered") {
    indicator.className = "wake-word-indicator triggered";
    if (label) label.textContent = "Otis détecté !";
    setTimeout(() => updateWakeWordIndicator(), 1500);
    return;
  }

  if (
    wakeWordPaused ||
    isRecording ||
    audioFocusManager.isDucking() ||
    (typeof document !== "undefined" && document.hidden)
  ) {
    indicator.className = "wake-word-indicator paused";
    indicator.title = "Mains-libres en pause. Cliquez pour désactiver.";
    if (label) label.textContent = "Otis en pause";
  } else {
    indicator.className = "wake-word-indicator listening";
    indicator.title = "Mains-libres actif. Cliquez pour désactiver et protéger votre musique.";
    if (label) label.textContent = "Otis à l'écoute";
  }
}

export function setWakeWordEnabled(enabled) {
  state.wakeWordEnabled = !!enabled;
  try {
    localStorage.setItem("pah_wake_word_enabled", state.wakeWordEnabled ? "true" : "false");
  } catch (e) {}

  if (state.wakeWordEnabled) {
    startWakeWordDetection(onWakeWordCallback || defaultWakeTrigger);
  } else {
    stopWakeWordDetection();
    audioFocusManager.releaseAllDucking();
  }
  updateWakeWordIndicator();
}

export function toggleWakeWord() {
  const next = !state.wakeWordEnabled;
  setWakeWordEnabled(next);

  // Synchroniser la case à cocher des réglages si présente dans le DOM
  const toggle = document.getElementById("wake-word-toggle");
  if (toggle) toggle.checked = next;

  return next;
}

export function pauseWakeWordDetector() {
  wakeWordPaused = true;
  updateWakeWordIndicator();
  if (voskDetector) voskDetector.stop();
}

export function resumeWakeWordDetector() {
  wakeWordPaused = false;
  updateWakeWordIndicator();
  if (state.wakeWordEnabled && !isRecording && !audioFocusManager.isDucking()) {
    startWakeWordDetection(onWakeWordCallback || defaultWakeTrigger);
  }
}

export function stopWakeWordDetection() {
  wakeWordPaused = false;
  updateWakeWordIndicator();
  if (voskDetector) voskDetector.stop();
}

// Détection locale (Vosk, micro brut) : la Web Speech API continue était relancée toutes les ~5 s par
// Chrome Android et coupait la musique à chaque relance.
function getVoskDetector() {
  if (!voskDetector) {
    voskDetector = new VoskWakeWordDetector({
      onWake: handleLocalWake,
      log: (message) => voiceDiagLog.record("otis", message),
    });
  }
  return voskDetector;
}

// « Otis » → bip → dictée : la commande est dite après le bip (pas de commande enchaînée).
function handleLocalWake() {
  voiceDiagLog.record("otis", "Réveil : bip puis dictée");
  updateWakeWordIndicator("triggered");
  playWakeChime();
  triggerWakeCapture("");
}

function handleWakeEngineFailure(err) {
  console.error("[WakeWord] Détection locale indisponible :", err);
  voiceDiagLog.record("otis", `Échec, mains-libres désactivé : ${err.message}`);
  showToastError(
    `Détection locale du mot-clé indisponible : ${err.message}. Mains-libres désactivé, le bouton micro reste utilisable.`,
    "Mot-clé « Otis »"
  );
  setWakeWordEnabled(false);
  const toggle = document.getElementById("wake-word-toggle");
  if (toggle) toggle.checked = false;
}

export function startWakeWordDetection(onWakeCallback = null) {
  if (onWakeCallback) {
    onWakeWordCallback = onWakeCallback;
  } else if (!onWakeWordCallback) {
    onWakeWordCallback = defaultWakeTrigger;
  }

  if (!state.wakeWordEnabled) {
    updateWakeWordIndicator();
    return;
  }
  if (wakeWordPaused || isRecording || (typeof document !== "undefined" && document.hidden)) {
    updateWakeWordIndicator();
    return;
  }

  const detector = getVoskDetector();
  if (detector.isRunning) return;
  voiceDiagLog.record("otis", "Démarrage de l'écoute du mot-clé");

  // Premier chargement du modèle (≈ 45 Mo, une seule fois) : prévenir seulement s'il ne vient pas du cache.
  const slowLoadTimer = setTimeout(() => {
    showToastInfo("Préparation du mot-clé « Otis » : téléchargement du modèle (≈ 45 Mo, une seule fois)…", "Otis");
  }, 2000);

  detector
    .start()
    .then(() => updateWakeWordIndicator())
    .catch(handleWakeEngineFailure)
    .finally(() => clearTimeout(slowLoadTimer));
}

// Module de Calibrage In-App Guidé
export function startWakeWordCalibration(onProgress, onDone) {
  if (!SpeechRecognition) {
    if (onDone) onDone(false, "Reconnaissance vocale non disponible.");
    return;
  }

  pauseWakeWordDetector();
  try {
    const calibRec = new SpeechRecognition();
    calibRec.lang = "fr-FR";
    calibRec.continuous = false;
    calibRec.interimResults = false;

    if (onProgress) onProgress("listening", "Dites « Otis » clairement ou essoufflé...");

    calibRec.onresult = (evt) => {
      if (evt.results.length > 0) {
        const heard = evt.results[0][0].transcript.toLowerCase().trim();
        addCustomWakeVariant(heard);
        if (onDone) onDone(true, heard);
      }
    };

    calibRec.onerror = (e) => {
      console.warn("[Calibration] Erreur:", e);
      let errMsg = e?.error || "Erreur de capture";
      if (e?.error === "no-speech") errMsg = "Aucune parole détectée. Rapprochez-vous du micro et réessayez.";
      if (e?.error === "not-allowed") errMsg = "Accès au micro refusé dans le navigateur.";
      if (onDone) onDone(false, errMsg);
      resumeWakeWordDetector();
    };

    calibRec.onend = () => {
      resumeWakeWordDetector();
    };

    calibRec.start();
  } catch (err) {
    if (onDone) onDone(false, err.message);
    resumeWakeWordDetector();
  }
}

export function addCustomWakeVariant(variant) {
  if (!variant) return;
  const clean = variant.toLowerCase().trim();
  if (!state.wakeWordCustomVariants) state.wakeWordCustomVariants = [];
  if (!state.wakeWordCustomVariants.includes(clean)) {
    state.wakeWordCustomVariants.push(clean);
    localStorage.setItem("pah_wake_word_custom_variants", JSON.stringify(state.wakeWordCustomVariants));
  }
}

export function removeCustomWakeVariant(variant) {
  if (!variant || !state.wakeWordCustomVariants) return;
  const clean = variant.toLowerCase().trim();
  state.wakeWordCustomVariants = state.wakeWordCustomVariants.filter((v) => v !== clean);
  localStorage.setItem("pah_wake_word_custom_variants", JSON.stringify(state.wakeWordCustomVariants));
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
  const micBtn = document.getElementById("mic-btn");
  const voiceBarArea = document.getElementById("voice-bar-area");
  const interimTranscript = document.getElementById("interim-transcript");

  legacyRecognition = new SpeechRecognition();
  legacyRecognition.lang = "fr-FR";
  legacyRecognition.interimResults = true;
  legacyRecognition.continuous = false;

  legacyRecognition.onstart = () => {
    setMicListening(true);
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
    setMicListening(false);
    if (voiceBarArea) voiceBarArea.classList.remove("active");
    if (e.error === "not-allowed" && onNotAllowedCallback) onNotAllowedCallback();
  };

  legacyRecognition.onend = () => {
    setMicListening(false);
    if (voiceBarArea) voiceBarArea.classList.remove("active");
  };

  if (micBtn) {
    micBtn.addEventListener("click", () => {
      try { legacyRecognition.start(); } catch (e) {}
    });
  }
}
