// Personal Assistant Hub - PWA Entrypoint & Modular Orchestrator
import { state, initTheme } from "./js/config.js";
import { audioFocusManager } from "./js/audio_focus.js";
import { SpeechRecognition, initSpeechRecognition } from "./js/mic_capture.js";
import {
  initChatView, sendInteraction, sendAudioInteraction, appendAssistantMessage, handleOfflineSyncedResponse,
} from "./js/views/chat_view.js";
import { initShoppingView } from "./js/views/shopping_view.js";
import { initTasksView } from "./js/views/tasks_view.js";
import { initMealsView } from "./js/views/meals_view.js";
import { initSportView } from "./js/views/sport_view.js";
import { openTrophies } from "./js/views/sport/sport_sheet.js";
import { initSecondBrainView } from "./js/views/second_brain_view.js";
import { initSettingsView } from "./js/views/settings_view.js";
import { initOfflineSync, syncOutbox } from "./js/offline_outbox.js";
import { sectionForAction } from "./js/ui_shell.js";
import { initShell } from "./js/app_shell.js";
import { initHandsFreeSwitch } from "./js/hands_free.js";
import { registerServiceWorker } from "./js/sw_register.js";

// Export / Référence SpeechRecognition pour les vérifications de compatibilité
export { SpeechRecognition };

document.addEventListener("DOMContentLoaded", () => {
  // 1. Initialisation Audio Focus (Mode Ambient non-intrusif) & Thème
  audioFocusManager.initAudioSession();
  initTheme();

  // 2. Éléments globaux
  const btnTtsToggle = document.getElementById("btn-tts-toggle");
  // (Réglages & voix : feuille dédiée, voir js/views/settings_view.js.)

  // 4. Initialisation TTS (Bouton switch)
  function updateTtsButtonState() {
    if (!btnTtsToggle) return;
    btnTtsToggle.setAttribute("aria-pressed", state.ttsEnabled ? "true" : "false");
    if (state.ttsEnabled) {
      btnTtsToggle.classList.add("active");
      btnTtsToggle.title = "Voix activée (cliquez pour couper)";
    } else {
      btnTtsToggle.classList.remove("active");
      btnTtsToggle.title = "Voix coupée (cliquez pour activer)";
    }
  }
  updateTtsButtonState();

  if (btnTtsToggle) {
    btnTtsToggle.addEventListener("click", () => {
      state.ttsEnabled = !state.ttsEnabled;
      localStorage.setItem("pah_tts_enabled", state.ttsEnabled ? "true" : "false");
      updateTtsButtonState();
      if (!state.ttsEnabled && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    });
  }

  // 6. Reconnaissance Vocale Haute-Fidélité (VAD & MediaRecorder Audio)
  initSpeechRecognition(
    (transcript) => sendInteraction(transcript),
    () => appendAssistantMessage("Accès au microphone refusé. Veuillez autoriser le micro dans votre navigateur."),
    (audioBlob) => sendAudioInteraction(audioBlob)
  );

  // 7. Initialisation des Vues Métier
  initChatView();
  initSecondBrainView();
  initShoppingView();
  initTasksView();
  initMealsView();
  initSportView();

  // 8. Navigation : menu burger + feuilles (js/app_shell.js)
  const shell = initShell();

  // 9. Réglages & voix : feuille dédiée (ancienne modale) ; la croix ferme sans enregistrer.
  initSettingsView({ close: () => shell.manager.closeTop() });

  // Mains-libres « Otis » : interrupteur du menu et témoin (js/hands_free.js ; feuille Réglages : settings_view.js)
  initHandsFreeSwitch();

  // 10. Gestion des raccourcis d'URL (?action=...) : ouvrent la feuille correspondante
  const shortcut = sectionForAction(new URLSearchParams(window.location.search).get("action"));
  if (shortcut) {
    shell.openSection(shortcut.section);
    if (shortcut.subview === "gamification") openTrophies();
  }

  // 11. Enregistrement PWA Service Worker
  registerServiceWorker();

  // 12. Initialisation File d'Attente Hors-Ligne & Synchronisation PWA
  const outboxIndicator = document.getElementById("offline-outbox-indicator");
  if (outboxIndicator) {
    outboxIndicator.addEventListener("click", () => {
      syncOutbox();
    });
  }
  initOfflineSync((item, data) => {
    handleOfflineSyncedResponse(item, data);
  });
});
