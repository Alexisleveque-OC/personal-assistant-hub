// Vue Assistant Conversationnel / Chat & Vocal
import { speak, showUndoToast, hideUndoToast } from "../speech.js";
import { postInteract, postInteractAudio } from "../api.js";

const chatStream = document.getElementById("chat-stream");
const queryForm = document.getElementById("query-form");
const queryInput = document.getElementById("query-input");

export function appendUserMessage(text) {
  if (!chatStream) return;
  const bubble = document.createElement("div");
  bubble.className = "chat-bubble user";
  bubble.textContent = text;
  chatStream.appendChild(bubble);
  bubble.scrollIntoView({ behavior: "smooth" });
}

export function appendAssistantMessage(text) {
  if (!chatStream) return;
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
  btnReplay.addEventListener("click", () => speak(text));

  bubble.scrollIntoView({ behavior: "smooth" });
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
  } catch (err) {
    appendAssistantMessage("Impossible de joindre le serveur. Vérifiez la connexion.");
  }
}

export async function sendAudioInteraction(audioBlob) {
  appendUserMessage("🎤 Envoi du message vocal...");
  try {
    const res = await postInteractAudio(audioBlob);

    if (res.status === 401) {
      appendAssistantMessage("Erreur 401 : Clé API manquante ou invalide. Cliquez sur l'engrenage pour la renseigner.");
      return;
    }

    if (!res.ok) {
      appendAssistantMessage(`Erreur serveur (${res.status}).`);
      return;
    }

    const data = await res.json();

    // Remplacer le texte temporaire par la transcription exacte
    const lastUserBubble = chatStream.querySelector(".chat-bubble.user:last-of-type");
    if (lastUserBubble && data.user_transcription) {
      lastUserBubble.textContent = `🎤 ${data.user_transcription}`;
    }

    appendAssistantMessage(data.spoken_response);
    speak(data.spoken_response);
    handleUndoToast(data);
  } catch (err) {
    appendAssistantMessage("Impossible de joindre le serveur. Vérifiez la connexion.");
  }
}

export function initChatView() {
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

  document.querySelectorAll(".chip-btn").forEach((chip) => {
    chip.addEventListener("click", () => {
      const text = chip.getAttribute("data-query") || chip.textContent.trim();
      sendInteraction(text);
    });
  });
}
