// Personal Assistant Hub - PWA Entrypoint & Modular Orchestrator
import { state, initTheme } from "./js/config.js";
import {
  SpeechRecognition,
  populateVoiceList,
  speak,
  initSpeechRecognition,
} from "./js/speech.js";
import { fetchLlmStats } from "./js/api.js";
import { initChatView, sendInteraction, sendAudioInteraction, appendAssistantMessage } from "./js/views/chat_view.js";
import { initShoppingView, fetchShoppingList } from "./js/views/shopping_view.js";
import { initMealsView, fetchMealToday, fetchMealWeek } from "./js/views/meals_view.js";
import { initSportView, switchSportSubview } from "./js/views/sport_view.js";
import { initSecondBrainView, loadSecondBrainNotes, loadSecondBrainCategories } from "./js/views/second_brain_view.js";

// Export / Référence SpeechRecognition pour les vérifications de compatibilité
export { SpeechRecognition };

document.addEventListener("DOMContentLoaded", () => {
  // 1. Initialisation Thème (Cocooning Clair / Botanique Sombre)
  initTheme();

  // 2. Éléments globaux
  const btnTtsToggle = document.getElementById("btn-tts-toggle");
  const btnSettings = document.getElementById("btn-settings");
  const settingsModal = document.getElementById("settings-modal");
  const btnCloseSettings = document.getElementById("btn-close-settings");
  const btnSaveSettings = document.getElementById("btn-save-settings");
  const apiKeyInput = document.getElementById("api-key-input");
  const voiceSelect = document.getElementById("voice-select");
  const btnTestVoice = document.getElementById("btn-test-voice");
  const pushToTalkToggle = document.getElementById("push-to-talk-toggle");
  const wakeWordToggle = document.getElementById("wake-word-toggle");
  const vadSilenceSelect = document.getElementById("vad-silence-select");
  const navItems = document.querySelectorAll(".nav-item");

  const views = {
    chat: document.getElementById("view-chat"),
    "second-brain": document.getElementById("view-second-brain"),
    shopping: document.getElementById("view-shopping"),
    meals: document.getElementById("view-meals"),
    sport: document.getElementById("view-sport")
  };

  // 3. Initialisation de la clé API
  if (apiKeyInput) apiKeyInput.value = state.apiKey;

  // 4. Initialisation TTS (Bouton switch)
  function updateTtsButtonState() {
    if (!btnTtsToggle) return;
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

  // 5. Catalogue des voix & Test
  populateVoiceList(voiceSelect);
  if ("speechSynthesis" in window && window.speechSynthesis.onvoiceschanged !== undefined) {
    window.speechSynthesis.onvoiceschanged = () => populateVoiceList(voiceSelect);
  }

  if (btnTestVoice) {
    btnTestVoice.addEventListener("click", () => {
      const chosenUri = voiceSelect ? voiceSelect.value : "";
      speak("Bonjour ! Voici un exemple avec la voix sélectionnée pour votre assistant personnel.", chosenUri);
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
  initMealsView();
  initSportView();

  // 8. Navigation par Onglets (Bottom Bar)
  navItems.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetView = btn.getAttribute("data-view");
      navItems.forEach((n) => n.classList.remove("active"));
      btn.classList.add("active");

      Object.keys(views).forEach((k) => {
        if (views[k]) views[k].classList.toggle("active", k === targetView);
      });

      if (targetView === "second-brain") {
        loadSecondBrainNotes();
        loadSecondBrainCategories();
      } else if (targetView === "shopping") {
        fetchShoppingList();
      } else if (targetView === "meals") {
        if (state.currentMealSubview === "today") {
          fetchMealToday();
        } else {
          fetchMealWeek();
        }
      } else if (targetView === "sport") {
        switchSportSubview(state.currentSportSubview);
      }
    });
  });

  // 9. Gestion Modal Paramètres & Stats LLM
  async function refreshLlmStats() {
    const statModel = document.getElementById("llm-stat-model");
    const statRequests = document.getElementById("llm-stat-requests");
    const statRemaining = document.getElementById("llm-stat-remaining");
    const statLatency = document.getElementById("llm-stat-latency");
    const quotaBadge = document.getElementById("llm-quota-badge");
    if (!statModel) return;

    try {
      const data = await fetchLlmStats();
      if (!data) return;
      statModel.textContent = data.model || "Indisponible";
      statRequests.textContent = `${data.daily_requests} / ${data.max_daily_requests}`;
      statRemaining.textContent = `${data.remaining_daily_requests} restantes`;
      statLatency.textContent = data.last_latency_ms ? `${data.last_latency_ms} ms` : "Aucune requête";

      if (quotaBadge) {
        if (data.quota_exceeded) {
          quotaBadge.textContent = "Quota atteint";
          quotaBadge.style.background = "#ef4444";
        } else if (data.remaining_daily_requests < 100) {
          quotaBadge.textContent = "Attention";
          quotaBadge.style.background = "#f59e0b";
        } else {
          quotaBadge.textContent = "Actif";
          quotaBadge.style.background = "#22c55e";
        }
      }
    } catch (e) {
      console.warn("Impossible de charger les statistiques LLM", e);
    }
  }

  if (btnSettings) {
    btnSettings.addEventListener("click", () => {
      if (apiKeyInput) apiKeyInput.value = state.apiKey;
      if (pushToTalkToggle) pushToTalkToggle.checked = !!state.pushToTalk;
      if (wakeWordToggle) wakeWordToggle.checked = !!state.wakeWordEnabled;
      if (vadSilenceSelect) vadSilenceSelect.value = String(state.vadSilenceMs || 2000);
      populateVoiceList(voiceSelect);
      refreshLlmStats();
      if (settingsModal) settingsModal.classList.add("active");
    });
  }

  if (btnCloseSettings) {
    btnCloseSettings.addEventListener("click", () => {
      if (settingsModal) settingsModal.classList.remove("active");
    });
  }

  if (btnSaveSettings) {
    btnSaveSettings.addEventListener("click", () => {
      state.apiKey = apiKeyInput ? apiKeyInput.value.trim() : "";
      localStorage.setItem("pah_api_key", state.apiKey);

      if (voiceSelect && voiceSelect.value) {
        state.selectedVoiceUri = voiceSelect.value;
        localStorage.setItem("pah_voice_uri", state.selectedVoiceUri);
      }

      if (pushToTalkToggle) {
        state.pushToTalk = pushToTalkToggle.checked;
        localStorage.setItem("pah_push_to_talk", state.pushToTalk ? "true" : "false");
      }

      if (wakeWordToggle) {
        state.wakeWordEnabled = wakeWordToggle.checked;
        localStorage.setItem("pah_wake_word_enabled", state.wakeWordEnabled ? "true" : "false");
      }

      if (vadSilenceSelect) {
        state.vadSilenceMs = parseInt(vadSilenceSelect.value, 10) || 2000;
        localStorage.setItem("pah_vad_silence_ms", String(state.vadSilenceMs));
      }

      if (settingsModal) settingsModal.classList.remove("active");
      appendAssistantMessage("Paramètres vocaux et ergonomie enregistrés avec succès !");
    });
  }

  // 10. Gestion des raccourcis d'URL (?action=...)
  const urlParams = new URLSearchParams(window.location.search);
  const actionParam = urlParams.get("action");
  if (actionParam === "shopping_list") {
    document.querySelector('.nav-item[data-view="shopping"]')?.click();
  } else if (actionParam === "meal_today") {
    document.querySelector('.nav-item[data-view="meals"]')?.click();
  } else if (actionParam === "sport_today") {
    document.querySelector('.nav-item[data-view="sport"]')?.click();
  } else if (actionParam === "sport_gamification") {
    document.querySelector('.nav-item[data-view="sport"]')?.click();
    const tabSportGamification = document.getElementById("tab-sport-gamification");
    if (tabSportGamification) tabSportGamification.click();
  } else if (actionParam === "second_brain") {
    document.querySelector('.nav-item[data-view="second-brain"]')?.click();
  }

  // 11. Enregistrement PWA Service Worker
  if ("serviceWorker" in navigator) {
    let refreshing = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (!refreshing) {
        refreshing = true;
        window.location.reload();
      }
    });

    navigator.serviceWorker.register("/sw.js")
      .then((reg) => {
        console.log("[PWA] Service Worker registered");
        reg.update();
      })
      .catch((err) => console.warn("[PWA] Service Worker registration failed:", err));
  }
});
