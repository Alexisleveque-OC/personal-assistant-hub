// Vue Assistant Conversationnel / Chat & Vocal avec Persistance 20 Messages
import { speak, showUndoToast, hideUndoToast } from "../speech.js";
import {
  postInteract,
  postInteractAudio,
  fetchSessionHistory,
  postResetSession,
  uploadSecondBrainImage,
} from "../api.js";
import { importSportScreenshotWithDatePrompt, DATE_CANCELLED_CODE } from "../screenshot_import.js";
import { getActiveSessionId, resetActiveSessionId } from "../config.js";
import { showToastInfo, showToastSuccess, showToastError } from "../toast.js";
import { enqueueTextRequest, enqueueAudioRequest, syncOutbox } from "../offline_outbox.js";

const chatStream = document.getElementById("chat-stream");
const queryForm = document.getElementById("query-form");
const queryInput = document.getElementById("query-input");

const CHAT_STORAGE_KEY = "pah_chat_ui_history";
const MAX_SAVED_MESSAGES = 20;

export function getStoredChatHistory() {
  try {
    return JSON.parse(localStorage.getItem(CHAT_STORAGE_KEY) || "[]");
  } catch (e) {
    return [];
  }
}

export function saveChatMessage(role, text) {
  if (!text) return;
  const history = getStoredChatHistory();
  history.push({ role, text, timestamp: new Date().toISOString() });
  const trimmed = history.slice(-MAX_SAVED_MESSAGES);
  try {
    localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(trimmed));
  } catch (e) {
    console.warn("Impossible de sauvegarder le message dans localStorage", e);
  }
}

export function updateLastUserMessage(newText) {
  const history = getStoredChatHistory();
  for (let i = history.length - 1; i >= 0; i--) {
    if (history[i].role === "user") {
      history[i].text = newText;
      break;
    }
  }
  try {
    localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(history));
  } catch (e) {}
}

function renderUserBubble(text, shouldScroll = true) {
  if (!chatStream) return null;
  const bubble = document.createElement("div");
  bubble.className = "chat-bubble user";
  bubble.textContent = text;
  chatStream.appendChild(bubble);
  if (shouldScroll) {
    bubble.scrollIntoView({ behavior: "smooth" });
  }
  return bubble;
}

function renderAssistantBubble(text, shouldScroll = true) {
  if (!chatStream) return null;
  const bubble = document.createElement("div");
  bubble.className = "chat-bubble assistant";

  const header = document.createElement("div");
  header.className = "bubble-header";
  header.innerHTML = `<span>Assistant Hub</span>
    <button class="btn-tts" title="Réécouter">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
        <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z"/>
      </svg>
    </button>`;

  const content = document.createElement("div");
  content.className = "bubble-content";
  content.textContent = text;

  bubble.appendChild(header);
  bubble.appendChild(content);
  chatStream.appendChild(bubble);

  const btnReplay = header.querySelector(".btn-tts");
  if (btnReplay) {
    btnReplay.addEventListener("click", () => speak(text));
  }

  if (shouldScroll) {
    bubble.scrollIntoView({ behavior: "smooth" });
  }
  return bubble;
}

export function appendUserMessage(text) {
  renderUserBubble(text, true);
  saveChatMessage("user", text);
}

export function appendAssistantMessage(text) {
  renderAssistantBubble(text, true);
  saveChatMessage("assistant", text);
}

export async function restoreChatHistory() {
  if (!chatStream) return;
  const localHistory = getStoredChatHistory();

  if (localHistory.length > 0) {
    chatStream.innerHTML = "";
    localHistory.forEach((msg) => {
      if (msg.role === "user") {
        renderUserBubble(msg.text, false);
      } else {
        renderAssistantBubble(msg.text, false);
      }
    });
    chatStream.lastElementChild?.scrollIntoView({ behavior: "auto" });
    return;
  }

  // Tenter de restaurer depuis le backend si localStorage était vide
  try {
    const res = await fetchSessionHistory();
    if (res && Array.isArray(res.history) && res.history.length > 0) {
      chatStream.innerHTML = "";
      const serverHistory = res.history.slice(-MAX_SAVED_MESSAGES);
      serverHistory.forEach((msg) => {
        if (msg.role === "user") {
          renderUserBubble(msg.text, false);
        } else {
          renderAssistantBubble(msg.text, false);
        }
      });
      try {
        localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(serverHistory));
      } catch (e) {}
      chatStream.lastElementChild?.scrollIntoView({ behavior: "auto" });
    }
  } catch (e) {
    console.debug("Pas d'historique de session serveur à restaurer");
  }
}

export function startNewThread() {
  const oldSessionId = getActiveSessionId();
  resetActiveSessionId();
  try {
    localStorage.removeItem(CHAT_STORAGE_KEY);
  } catch (e) {}

  postResetSession(oldSessionId).catch(() => {});

  if (chatStream) {
    chatStream.innerHTML = `
      <div class="chat-bubble assistant">
        <div class="bubble-header">
          <span>Assistant Hub</span>
        </div>
        <div class="bubble-content">
          ✨ Nouveau fil de discussion ouvert. Que puis-je faire pour toi ?
        </div>
      </div>
    `;
  }
}

function handleUndoToast(data) {
  if (!data) return;
  const d = data.data || {};

  // Si l'action vient d'annuler une opération, on masque le toast
  if (d.undone_action) {
    hideUndoToast();
    return;
  }

  // Détection d'une action réversible (note, apprentissage, courses)
  let actionDesc = null;
  if (d.note_id) {
    actionDesc = `Note enregistrée (${d.category || "idée"})`;
  } else if (d.learning_id) {
    actionDesc = "Correction mémorisée";
  } else if (d.items && Array.isArray(d.items) && d.items.length > 0) {
    actionDesc = `${d.items.length} article(s) ajouté(s)`;
  }

  if (actionDesc) {
    showUndoToast(actionDesc, () => {
      sendInteraction("annule ça");
    });
  }
}

export async function sendInteraction(text) {
  appendUserMessage(text);

  if (typeof navigator !== "undefined" && !navigator.onLine) {
    await enqueueTextRequest(text);
    appendAssistantMessage("⏳ Vous êtes actuellement hors-ligne (pas de réseau). Votre message a été enregistré localement et sera transmis automatiquement dès le retour de la connexion.");
    return;
  }

  try {
    const res = await postInteract(text);

    if (res.status === 401) {
      appendAssistantMessage("Erreur 401 : Clé API manquante ou invalide. Cliquez sur l'engrenage pour la renseigner.");
      return;
    }

    if (!res.ok) {
      appendAssistantMessage(`Erreur serveur (${res.status}).`);
      return;
    }

    const data = await res.json();
    appendAssistantMessage(data.spoken_response);
    speak(data.spoken_response);
    handleUndoToast(data);

    // Notification globale pour rafraîchir les vues métiers si une séance sport a été touchée
    const it = data.intent ? (data.intent.intent || "") : "";
    if (it.includes("sport") || (data.data && data.data.session)) {
      window.dispatchEvent(new CustomEvent("sport-data-updated"));
    }

    // Le réseau est pleinement fonctionnel : tenter de dépiler l'outbox s'il y a des requêtes en attente
    syncOutbox();
  } catch (err) {
    console.warn("[Chat] Échec envoi interaction:", err);
    await enqueueTextRequest(text);
    appendAssistantMessage("⏳ Réseau indisponible. Votre message a été enregistré localement et sera transmis automatiquement dès le retour de la connexion.");
  }
}

export async function sendAudioInteraction(audioBlob) {
  appendUserMessage("🎤 Envoi du message vocal...");

  if (typeof navigator !== "undefined" && !navigator.onLine) {
    await enqueueAudioRequest(audioBlob);
    appendAssistantMessage("⏳ Vous êtes actuellement hors-ligne (pas de réseau). Votre message vocal a été enregistré localement et sera transmis automatiquement dès le retour de la connexion.");
    return;
  }

  try {
    const res = await postInteractAudio(audioBlob);

    if (res.status === 401) {
      appendAssistantMessage("Erreur 401 : Clé API manquante ou invalide. Cliquez sur l'engrenage pour la renseigner.");
      return;
    }

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      appendAssistantMessage(errData.detail || `Erreur serveur (${res.status}) lors du traitement vocal.`);
      return;
    }

    const data = await res.json();

    // Remplacer le texte temporaire par la transcription exacte (transcribed_text ou user_transcription)
    const lastUserBubble = chatStream.querySelector(".chat-bubble.user:last-of-type");
    const transcription = data.transcribed_text || data.user_transcription;
    if (lastUserBubble && transcription) {
      const fullText = `🎤 ${transcription}`;
      lastUserBubble.textContent = fullText;
      updateLastUserMessage(fullText);
    }

    appendAssistantMessage(data.spoken_response);
    speak(data.spoken_response);
    handleUndoToast(data);

    const it = data.intent ? (data.intent.intent || "") : "";
    if (it.includes("sport") || (data.data && data.data.session)) {
      window.dispatchEvent(new CustomEvent("sport-data-updated"));
    }

    // Le réseau est pleinement fonctionnel : tenter de dépiler l'outbox s'il y a des requêtes en attente
    syncOutbox();
  } catch (err) {
    console.warn("[Chat] Échec envoi audio:", err);
    await enqueueAudioRequest(audioBlob);
    if (err && err.name === "AbortError") {
      appendAssistantMessage("⏳ Délai réseau dépassé. Votre message vocal a été enregistré localement et sera transmis dès le retour d'une connexion stable.");
    } else {
      appendAssistantMessage("⏳ Réseau indisponible. Votre message vocal a été enregistré localement et sera transmis automatiquement dès le retour de la connexion.");
    }
  }
}

export function handleOfflineSyncedResponse(item, data) {
  if (!data) return;

  // Afficher la bulle utilisateur synchronisée pour que l'historique de la conversation soit complet
  const userText = item.type === "text"
    ? item.query
    : (data.transcribed_text || data.user_transcription || "Message vocal");
  appendUserMessage(`🔄 [Rattrapage] ${userText}`);

  // Afficher la réponse d'Otis
  const synMsg = `🔄 [Synchronisé] ${data.spoken_response}`;
  appendAssistantMessage(synMsg);
  speak(data.spoken_response);
  handleUndoToast(data);

  const it = data.intent ? (data.intent.intent || "") : "";
  if (it.includes("sport") || (data.data && data.data.session)) {
    window.dispatchEvent(new CustomEvent("sport-data-updated"));
  }
}

export async function handleChatImageUpload(file) {
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    showToastError("Le fichier sélectionné n'est pas une image valide.", "Format non supporté");
    return;
  }

  appendUserMessage("📸 Envoi d'une capture d'écran...");
  const toastAnalyzing = showToastInfo("Analyse de la capture par Otis en cours...", "Analyse Otis", { duration: 0 });

  // 1. Tenter d'abord l'analyse en séance de sport running
  try {
    const sportRes = await importSportScreenshotWithDatePrompt(file, {
      onDatePrompt: () => toastAnalyzing.dismiss(),
    });
    toastAnalyzing.dismiss();

    const spokenMsg = sportRes.spoken_response || "Votre séance de sport a été importée avec succès !";
    appendAssistantMessage(spokenMsg);
    speak(spokenMsg);
    showToastSuccess(spokenMsg, "Séance de course importée ✅");
    window.dispatchEvent(new CustomEvent("sport-data-updated"));
    return;
  } catch (sportErr) {
    if (sportErr.code === DATE_CANCELLED_CODE) {
      toastAnalyzing.dismiss();
      appendAssistantMessage(sportErr.message);
      return;
    }
    const errText = String(sportErr.message || "");
    const isExplicitNonSport = errText.includes("ne semble pas être une capture") || errText.includes("non_sport_running") || errText.includes("400") || errText.includes("422");

    if (!isExplicitNonSport) {
      // C'était une séance de sport ou une erreur technique, ne pas polluer les notes
      toastAnalyzing.dismiss();
      console.error("Erreur technique import capture sport:", sportErr);
      const failMsg = `Désolé, l'analyse de votre capture de course a rencontré une erreur : ${sportErr.message}`;
      appendAssistantMessage(failMsg);
      showToastError(sportErr.message, "Erreur d'analyse sport");
      return;
    }
    console.debug("Image non sportive, tentative d'archivage dans le Second Cerveau...");
  }

  // 2. Si ce n'est manifestement pas du sport, tenter comme note dans le Second Cerveau
  try {
    const brainRes = await uploadSecondBrainImage(file);
    toastAnalyzing.dismiss();

    const noteTitle = (brainRes.note && brainRes.note.title) ? brainRes.note.title : "Nouvelle note";
    const noteMsg = `Cette image n'est pas une course à pied. Je l'ai enregistrée dans vos notes du Second Cerveau sous "${noteTitle}".`;
    appendAssistantMessage(noteMsg);
    speak(noteMsg);
    showToastSuccess("Capture enregistrée dans vos notes.", "Second Cerveau ✅");
    return;
  } catch (brainErr) {
    toastAnalyzing.dismiss();
    console.error("Échec des deux analyses d'image:", brainErr);
    const failMsg = "Désolé, je n'ai pas pu reconnaître de séance de sport ni de document exploitable dans cette image.";
    appendAssistantMessage(failMsg);
    showToastError("Impossible d'extraire les informations de l'image.", "Échec d'analyse");
  }
}

export function initChatView() {
  // Réhydrater immédiatement les 20 derniers messages
  restoreChatHistory();

  if (queryForm) {
    queryForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const val = queryInput.value.trim();
      if (val) {
        queryInput.value = "";
        sendInteraction(val);
      }
    });
  }

  // Upload d'image direct depuis la barre de saisie
  const btnChatUpload = document.getElementById("btn-chat-upload-image");
  const fileChatInput = document.getElementById("chat-file-image-input");
  if (btnChatUpload && fileChatInput) {
    btnChatUpload.addEventListener("click", () => fileChatInput.click());
    fileChatInput.addEventListener("change", (e) => {
      const file = e.target.files && e.target.files[0];
      if (file) {
        handleChatImageUpload(file);
        fileChatInput.value = "";
      }
    });
  }

  // Support du collage (Paste / Ctrl+V) d'une capture dans le Chat
  window.addEventListener("paste", (e) => {
    const activeView = document.getElementById("view-chat");
    if (!activeView || !activeView.classList.contains("active")) return;

    const items = (e.clipboardData || e.originalEvent.clipboardData)?.items;
    if (!items) return;

    for (let i = 0; i < items.length; i++) {
      if (items[i].type.indexOf("image") !== -1) {
        const file = items[i].getAsFile();
        if (file) {
          e.preventDefault();
          handleChatImageUpload(file);
          break;
        }
      }
    }
  });

  // Bouton Nouveau fil dans le header
  const btnNewChat = document.getElementById("btn-new-chat");
  if (btnNewChat) {
    btnNewChat.addEventListener("click", () => {
      startNewThread();
    });
  }

  // Chip Nouveau fil
  const chipNewChat = document.getElementById("chip-new-chat");
  if (chipNewChat) {
    chipNewChat.addEventListener("click", () => {
      startNewThread();
    });
  }

  document.querySelectorAll(".chip-btn").forEach((chip) => {
    if (chip.id === "chip-new-chat") return;
    chip.addEventListener("click", () => {
      const text = chip.getAttribute("data-query") || chip.textContent.trim();
      sendInteraction(text);
    });
  });
}

