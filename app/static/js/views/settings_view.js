// Feuille « Réglages & voix » (ancienne modale, refonte UX étape 7 suite ; contenu inchangé).
// Voix de synthèse (choix + extrait), micro (push-to-talk, mains-libres, délai de silence), clé d'API, quotas Gemini.
// Les champs sont relus à chaque ouverture ; « Enregistrer » applique, la croix ferme sans enregistrer
// (sauf « Mains-libres », appliqué dès qu'on le touche, comme l'interrupteur du menu).
import { state } from "../config.js";
import { fetchLlmStats } from "../api.js";
import { populateVoiceList, speak } from "../tts.js";
import { setupMicButtonBehavior } from "../mic_capture.js";
import { setWakeWordEnabled } from "../wake_word.js";
import { llmStatsView } from "../settings_model.js";
import { showToastInfo, showToastSuccess } from "../toast.js";

const form = document.getElementById("settings-form");
const apiKeyInput = document.getElementById("api-key-input");
const voiceSelect = document.getElementById("voice-select");
const testVoiceButton = document.getElementById("btn-test-voice");
const pushToTalkToggle = document.getElementById("push-to-talk-toggle");
const wakeWordToggle = document.getElementById("wake-word-toggle");
const vadSilenceSelect = document.getElementById("vad-silence-select");

function setText(id, text) {
  const node = document.getElementById(id);
  if (node) node.textContent = text;
}

async function refreshLlmStats() {
  let data = null;
  try {
    data = await fetchLlmStats();
  } catch (err) {
    console.warn("[Réglages] Statistiques Gemini indisponibles :", err);
  }
  const view = llmStatsView(data);
  setText("llm-stat-model", view.model);
  setText("llm-stat-requests", view.requests);
  setText("llm-stat-remaining", view.remaining);
  setText("llm-stat-latency", view.latency);
  const badge = document.getElementById("llm-quota-badge");
  if (badge) {
    badge.textContent = view.badge.text;
    badge.className = `badge badge--${view.badge.tone}`;
  }
}

// Ouverture de la feuille : les champs reflètent les réglages enregistrés.
export function loadSettings() {
  if (apiKeyInput) apiKeyInput.value = state.apiKey;
  if (pushToTalkToggle) pushToTalkToggle.checked = !!state.pushToTalk;
  if (wakeWordToggle) wakeWordToggle.checked = !!state.wakeWordEnabled;
  if (vadSilenceSelect) vadSilenceSelect.value = String(state.vadSilenceMs || 2000);
  populateVoiceList(voiceSelect);
  refreshLlmStats();
}

function save() {
  state.apiKey = apiKeyInput ? apiKeyInput.value.trim() : "";
  localStorage.setItem("pah_api_key", state.apiKey);

  if (voiceSelect && voiceSelect.value) {
    state.selectedVoiceUri = voiceSelect.value;
    localStorage.setItem("pah_voice_uri", state.selectedVoiceUri);
  }

  if (pushToTalkToggle) {
    state.pushToTalk = pushToTalkToggle.checked;
    localStorage.setItem("pah_push_to_talk", state.pushToTalk ? "true" : "false");
    setupMicButtonBehavior();
  }

  if (wakeWordToggle) setWakeWordEnabled(wakeWordToggle.checked); // enregistre aussi pah_wake_word_enabled

  if (vadSilenceSelect) {
    state.vadSilenceMs = parseInt(vadSilenceSelect.value, 10) || 2000;
    localStorage.setItem("pah_vad_silence_ms", String(state.vadSilenceMs));
  }
}

// `close` : ferme la feuille après l'enregistrement (gestionnaire de feuilles d'app.js).
export function initSettingsView({ close }) {
  populateVoiceList(voiceSelect);
  if ("speechSynthesis" in window && window.speechSynthesis.onvoiceschanged !== undefined) {
    window.speechSynthesis.onvoiceschanged = () => populateVoiceList(voiceSelect);
  }

  if (testVoiceButton) {
    testVoiceButton.addEventListener("click", () => {
      speak("Bonjour ! Voici un exemple avec la voix sélectionnée pour votre assistant personnel.", voiceSelect ? voiceSelect.value : "");
    });
  }

  if (wakeWordToggle) {
    wakeWordToggle.addEventListener("change", (e) => {
      setWakeWordEnabled(e.target.checked); // l'interrupteur du menu suit (updateWakeWordIndicator)
      if (e.target.checked) showToastInfo("Mains-libres 'Otis' activé.", "Otis à l'écoute");
      else showToastSuccess("Mode au clic activé : micro coupé, musique à 100%.", "Micro au clic");
    });
  }

  if (form) {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      save();
      close();
      showToastSuccess("Voix, micro et clé d'API enregistrés.", "Réglages enregistrés");
    });
  }
}
