// Capture micro de la dictée : bouton hybride (maintenir / toucher), MediaRecorder, détection de silence (VAD),
// capture à usage unique (« Dicte ta séance ») et repli Web Speech API. Réveil « Otis » → defaultWakeTrigger.
import { state } from "./config.js";
import { audioFocusManager } from "./audio_focus.js";
import { showToastInfo } from "./toast.js";
import { voiceDiagLog } from "./voice_diag_log.js";
import {
  extractCommandAfterWakeWord, pauseWakeWordDetector, registerWakeCapture, resumeWakeWordDetector, startWakeWordDetection,
} from "./wake_word.js";

export const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

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

// Callbacks et état de la capture
let savedOnResultCallback = null;
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

// État « écoute » du micro : `.is-listening` sur le bouton (hub.css), `.recording` sur son conteneur.
// Relu à chaque fois : le bouton est remplacé par setupMicButtonBehavior() et la barre de saisie change de feuille.
// `mic-listening` : les autres boutons de dictée (ex. « Dicte ta séance ») suivent l'état de l'écoute.
function setMicListening(listening) {
  const wrapper = document.getElementById("mic-wrapper");
  const button = document.getElementById("mic-btn");
  if (wrapper) wrapper.classList.toggle("recording", listening);
  if (button) button.classList.toggle("is-listening", listening);
  window.dispatchEvent(new CustomEvent("mic-listening", { detail: { listening, oneShot: !!oneShotTarget } }));
}

// Capture « à usage unique » (ex. « Dicte ta séance ») : le prochain enregistrement part vers `onBlob` au lieu
// d'Otis, avec les mêmes réglages (silence, baisse du son, pause du mot-clé). Faux si la dictée est indisponible.
let oneShotTarget = null;

export function captureOnce(onBlob) {
  if (!activeStartAudioCapture) return false;
  if (isRecording || isStartingCapture) {
    showToastInfo("Une dictée est déjà en cours.", "Micro");
    return false;
  }
  oneShotTarget = onBlob;
  activeStartAudioCapture(false);
  return true;
}

export function stopCapture() {
  if (activeStopAudioCapture) activeStopAudioCapture("bouton");
}

export function initSpeechRecognition(onResultCallback, onNotAllowedCallback, onAudioBlobCallback) {
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
        const target = oneShotTarget || onAudioBlobCallback; // capture à usage unique : une seule fois
        oneShotTarget = null;
        if (blob.size > 1000 && target) {
          voiceDiagLog.record("dictée", `Enregistrement de ${(blob.size / 1024).toFixed(1)} Ko transmis pour transcription`);
          target(blob);
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
      if (oneShotTarget) {
        oneShotTarget = null; // la dictée suivante repart vers Otis
        setMicListening(false);
      }
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

  activeStartAudioCapture = startAudioCapture;
  activeStopAudioCapture = stopAudioCapture;
  setupMicButtonBehavior();

  // Réveil « Otis » : enchaîne sur la dictée (ou envoie la commande dite après le mot-clé)
  registerWakeCapture({ onWake: defaultWakeTrigger, isBusy: () => isRecording });

  // Wake Word discret in-app ("Otis") si activé
  if (state.wakeWordEnabled) {
    startWakeWordDetection();
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
