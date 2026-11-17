// Mot-clé « Otis » (mains-libres) : détection locale Vosk, témoin du menu, pause pendant la lecture et la dictée.
// Couche basse : la capture micro s'y branche par registerWakeCapture() (pas d'import croisé).
import { state } from "./config.js";
import { audioFocusManager } from "./audio_focus.js";
import { VoskWakeWordDetector } from "./wake_word_vosk.js";
import { showToastError, showToastInfo } from "./toast.js";
import { voiceDiagLog } from "./voice_diag_log.js";

let voskDetector = null;
let wakeWordPaused = false;
let onWakeWordCallback = null;
let isCaptureBusy = () => false;

/** Branche la capture micro : `onWake` reçoit la transcription du réveil, `isBusy` dit si une dictée est en cours. */
export function registerWakeCapture({ onWake, isBusy }) {
  onWakeWordCallback = onWake;
  isCaptureBusy = isBusy;
}

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

export function triggerWakeCapture(detectedTranscript = "") {
  if (onWakeWordCallback) onWakeWordCallback(detectedTranscript);
}

export function updateWakeWordIndicator(statusOverride = null) {
  // Interrupteur « Mains-libres » du menu (refonte UX) : suit l'état réel (réglages, coupure auto sur échec).
  const wakeSwitch = document.getElementById("wake-word-switch");
  if (wakeSwitch) wakeSwitch.checked = !!state.wakeWordEnabled;
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
    isCaptureBusy() ||
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
    startWakeWordDetection();
  } else {
    stopWakeWordDetection();
    audioFocusManager.releaseAllDucking();
  }
  updateWakeWordIndicator();
}

export function pauseWakeWordDetector() {
  wakeWordPaused = true;
  updateWakeWordIndicator();
  if (voskDetector) voskDetector.stop();
}

export function resumeWakeWordDetector() {
  wakeWordPaused = false;
  updateWakeWordIndicator();
  if (state.wakeWordEnabled && !isCaptureBusy() && !audioFocusManager.isDucking()) {
    startWakeWordDetection();
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

export function startWakeWordDetection() {
  if (!state.wakeWordEnabled) {
    updateWakeWordIndicator();
    return;
  }
  if (wakeWordPaused || isCaptureBusy() || (typeof document !== "undefined" && document.hidden)) {
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
