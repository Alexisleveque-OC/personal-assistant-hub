// Vue Assistant Conversationnel / Chat & Vocal avec Persistance 20 Messages
import { speak } from "../tts.js";
import { showUndoToast, hideUndoToast } from "../undo_bar.js";
import {
  postInteract,
  postInteractAudio,
  fetchSessionHistory,
  postResetSession,
  uploadSecondBrainImage,
} from "../api.js";
import { importSportScreenshotWithDatePrompt, DATE_CANCELLED_CODE } from "../screenshot_import.js";
import { state, getActiveSessionId, resetActiveSessionId } from "../config.js";
import { withDue } from "../tasks_model.js";
import { clearComposerDue } from "./task_due_picker.js";
import { showToastInfo, showToastSuccess, showToastError } from "../toast.js";
import { enqueueTextRequest, enqueueAudioRequest, syncOutbox } from "../offline_outbox.js";
import { voiceDiagLog } from "../voice_diag_log.js";

const chatStream = document.getElementById("chat-stream");
const queryForm = document.getElementById("query-form");
const queryInput = document.getElementById("query-input");

// Refonte UX : la conversation est dans la feuille « Conversation » ; fermée, on ne fait pas défiler la page.
function isHomeVisible() {
  const conversation = document.getElementById("view-conversation");
  return !conversation || conversation.classList.contains("active");
}

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

// Messages du fil (refonte UX) : les tiens à droite, ceux d'Otis en carte avec son avatar et « Réécouter ».
const SVG_NS = "http://www.w3.org/2000/svg";

function speakerIcon() {
  const svg = document.createElementNS(SVG_NS, "svg");
  for (const [name, value] of Object.entries({
    viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "2",
    "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true",
  })) svg.setAttribute(name, value);
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", "M4 10v4h4l5 4V6L8 10H4zM16.5 9a4 4 0 0 1 0 6");
  svg.append(path);
  return svg;
}

function otisHead() {
  const head = document.createElement("div");
  head.className = "msg__head";
  const avatar = document.createElement("img");
  avatar.className = "avatar-otis";
  avatar.src = "/static/icons/logo-otis.svg";
  avatar.alt = "";
  const who = document.createElement("span");
  who.className = "msg__who";
  who.textContent = "Otis";
  head.append(avatar, who);
  return head;
}

function scrollToMessage(node, shouldScroll) {
  if (shouldScroll && isHomeVisible()) node.scrollIntoView({ behavior: "smooth", block: "end" });
}

function renderUserBubble(text, shouldScroll = true) {
  if (!chatStream) return null;
  const bubble = document.createElement("div");
  bubble.className = "msg msg--user";
  bubble.textContent = text;
  chatStream.appendChild(bubble);
  scrollToMessage(bubble, shouldScroll);
  return bubble;
}

function renderAssistantBubble(text, shouldScroll = true) {
  if (!chatStream) return null;
  const bubble = document.createElement("div");
  bubble.className = "msg msg--otis";
  const head = otisHead();
  const replay = document.createElement("button");
  replay.type = "button";
  replay.className = "icon-btn msg__replay";
  replay.setAttribute("aria-label", "Réécouter");
  replay.append(speakerIcon());
  replay.addEventListener("click", () => speak(text));
  head.append(replay);
  const content = document.createElement("p");
  content.className = "msg__text";
  content.textContent = text;
  bubble.append(head, content);
  chatStream.appendChild(bubble);
  scrollToMessage(bubble, shouldScroll);
  return bubble;
}

// Ouverture de la feuille « Conversation » : le dernier message est visible.
export function scrollConversationToEnd() {
  if (chatStream && chatStream.lastElementChild) chatStream.lastElementChild.scrollIntoView({ block: "end" });
}

export function appendUserMessage(text) {
  renderUserBubble(text, true);
  saveChatMessage("user", text);
}

// Bulle « Otis réfléchit… » : un tour agent prend plusieurs secondes, l'utilisateur voit que la demande avance.
// Jamais sauvegardée dans l'historique local.
let thinkingBubble = null;

function showThinkingIndicator() {
  if (!chatStream || thinkingBubble) return;
  thinkingBubble = document.createElement("div");
  thinkingBubble.className = "msg msg--otis msg--thinking";
  thinkingBubble.setAttribute("role", "status");
  const text = document.createElement("p");
  text.className = "msg__text";
  text.textContent = "Otis réfléchit";
  const dots = document.createElement("span");
  dots.className = "msg__dots";
  dots.setAttribute("aria-hidden", "true");
  for (let i = 0; i < 3; i++) dots.append(document.createElement("span"));
  text.append(dots);
  thinkingBubble.append(otisHead(), text);
  chatStream.appendChild(thinkingBubble);
  scrollToMessage(thinkingBubble, true);
}

function hideThinkingIndicator() {
  if (thinkingBubble) thinkingBubble.remove();
  thinkingBubble = null;
}

export function appendAssistantMessage(text) {
  renderAssistantBubble(text, true);
  saveChatMessage("assistant", text);
  // Refonte UX : app.js affiche la réponse en toast si une feuille est ouverte, puis la rafraîchit.
  window.dispatchEvent(new CustomEvent("otis-reply", { detail: { text } }));
}

export async function restoreChatHistory() {
  if (!chatStream) return;
  const localHistory = getStoredChatHistory();

  if (localHistory.length > 0) {
    chatStream.replaceChildren();
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
      chatStream.replaceChildren();
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
    chatStream.replaceChildren();
    renderAssistantBubble("Nouveau fil de discussion ouvert. Que puis-je faire pour toi ?", false);
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
    showThinkingIndicator();
    const res = await postInteract(text);
    hideThinkingIndicator();

    if (res.status === 401) {
      appendAssistantMessage("Erreur 401 : Clé API manquante ou invalide. Renseignez-la dans « Réglages & voix » (menu).");
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
    hideThinkingIndicator();
    await enqueueTextRequest(text);
    appendAssistantMessage("⏳ Réseau indisponible. Votre message a été enregistré localement et sera transmis automatiquement dès le retour de la connexion.");
  } finally {
    hideThinkingIndicator();
  }
}

export async function sendAudioInteraction(audioBlob) {
  appendUserMessage("🎤 Envoi du message vocal...");

  if (typeof navigator !== "undefined" && !navigator.onLine) {
    await enqueueAudioRequest(audioBlob);
    voiceDiagLog.record("envoi", "Hors-ligne : message vocal mis en attente");
    appendAssistantMessage("⏳ Vous êtes actuellement hors-ligne (pas de réseau). Votre message vocal a été enregistré localement et sera transmis automatiquement dès le retour de la connexion.");
    return;
  }

  const sentAt = performance.now();
  const elapsed = () => `${((performance.now() - sentAt) / 1000).toFixed(1)} s`;
  voiceDiagLog.record("envoi", `POST /interact/audio (${(audioBlob.size / 1024).toFixed(1)} Ko, ${audioBlob.type || "type inconnu"})`);
  try {
    showThinkingIndicator();
    const res = await postInteractAudio(audioBlob);
    hideThinkingIndicator(); // avant de chercher la dernière bulle utilisateur (:last-of-type)
    voiceDiagLog.record("envoi", `Réponse HTTP ${res.status} en ${elapsed()}`);

    if (res.status === 401) {
      appendAssistantMessage("Erreur 401 : Clé API manquante ou invalide. Renseignez-la dans « Réglages & voix » (menu).");
      return;
    }

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      voiceDiagLog.record("envoi", `Erreur affichée : ${errData.detail || "(sans détail)"}`);
      appendAssistantMessage(errData.detail || `Erreur serveur (${res.status}) lors du traitement vocal.`);
      return;
    }

    const data = await res.json();

    // Remplacer le texte temporaire par la transcription exacte (transcribed_text ou user_transcription)
    const userBubbles = chatStream.querySelectorAll(".msg--user");
    const lastUserBubble = userBubbles[userBubbles.length - 1];
    const transcription = data.transcribed_text || data.user_transcription;
    voiceDiagLog.record("envoi", `Transcription : « ${transcription || ""} »`);
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
    hideThinkingIndicator();
    await enqueueAudioRequest(audioBlob);
    voiceDiagLog.record("envoi", `Échec après ${elapsed()} (${err && err.name}: ${err && err.message}), message vocal mis en attente`);
    if (err && err.name === "AbortError") {
      appendAssistantMessage("⏳ Délai réseau dépassé. Votre message vocal a été enregistré localement et sera transmis dès le retour d'une connexion stable.");
    } else {
      appendAssistantMessage("⏳ Réseau indisponible. Votre message vocal a été enregistré localement et sera transmis automatiquement dès le retour de la connexion.");
    }
  } finally {
    hideThinkingIndicator();
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
    window.dispatchEvent(new CustomEvent("second-brain-updated"));
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
        // Feuille Tâches : date (et heure) choisies au calendrier jointes en clair au message.
        const due = state.uiContext === "taches" ? state.composerDue : null;
        sendInteraction(withDue(val, due));
        if (due) clearComposerDue();
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
    const activeView = document.getElementById("view-conversation");
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

  document.querySelectorAll("#chips-container [data-query]").forEach((chip) => {
    chip.addEventListener("click", () => {
      const text = chip.getAttribute("data-query") || chip.textContent.trim();
      sendInteraction(text);
    });
  });
}

