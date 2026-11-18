// Conversation avec Otis : messages texte et audio, session, statistiques LLM, journal, dernières actions.
import { state, getActiveSessionId } from "../config.js";
import { currentInteractionContext, getAuthHeaders } from "./http.js";

export async function postInteract(queryText, sessionId = null) {
  const finalSessionId = sessionId || getActiveSessionId();
  const res = await fetch("/api/v1/interact", {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ query: queryText, session_id: finalSessionId, context: currentInteractionContext() })
  });
  return res;
}

export async function postInteractAudio(audioBlob, sessionId = null) {
  const finalSessionId = sessionId || getActiveSessionId();
  const formData = new FormData();

  // Extension adaptée au type réel du Blob capté
  const mime = (audioBlob && audioBlob.type ? audioBlob.type : "").toLowerCase();
  let filename = "recording.webm";
  if (mime.includes("mp4")) {
    filename = "recording.mp4";
  } else if (mime.includes("ogg")) {
    filename = "recording.ogg";
  } else if (mime.includes("wav")) {
    filename = "recording.wav";
  }

  formData.append("audio_file", audioBlob, filename);
  formData.append("session_id", finalSessionId);
  formData.append("context", JSON.stringify(currentInteractionContext()));
  const headers = {};
  if (state.apiKey) {
    headers["X-API-Key"] = state.apiKey;
  }

  // Protection contre les blocages réseau matinaux via AbortController (timeout 25s)
  const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
  const timeoutId = controller ? setTimeout(() => controller.abort(), 25000) : null;

  try {
    const res = await fetch("/api/v1/interact/audio", {
      method: "POST",
      headers: headers,
      body: formData,
      signal: controller ? controller.signal : undefined,
    });
    if (timeoutId) clearTimeout(timeoutId);
    return res;
  } catch (err) {
    if (timeoutId) clearTimeout(timeoutId);
    throw err;
  }
}

export async function fetchSessionHistory(sessionId = null) {
  const finalSessionId = sessionId || getActiveSessionId();
  const headers = getAuthHeaders();
  const res = await fetch(`/api/v1/session/history?session_id=${encodeURIComponent(finalSessionId)}`, { headers });
  if (!res.ok) return { session_id: finalSessionId, history: [] };
  return await res.json();
}

export async function postResetSession(sessionId = null) {
  const finalSessionId = sessionId || getActiveSessionId();
  const headers = getAuthHeaders();
  const res = await fetch(`/api/v1/session/reset?session_id=${encodeURIComponent(finalSessionId)}`, {
    method: "POST",
    headers,
  });
  if (!res.ok) return { status: "error" };
  return await res.json();
}

export async function fetchLlmStats() {
  const headers = state.apiKey ? { "x-api-key": state.apiKey } : {};
  const res = await fetch("/api/v1/llm/stats", { headers });
  if (!res.ok) return null;
  return await res.json();
}

export async function fetchConversationLogs({ limit = 50, offset = 0, success = null } = {}) {
  const headers = state.apiKey ? { "x-api-key": state.apiKey } : {};
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (success !== null) params.append("success", String(success));

  const res = await fetch(`/api/v1/system/conversation-logs?${params.toString()}`, { headers });
  if (!res.ok) throw new Error("Erreur chargement journal conversationnel : " + res.status);
  return await res.json();
}

export async function postConversationFeedback(logId, payload) {
  const res = await fetch(`/api/v1/system/conversation-logs/${logId}/feedback`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(payload)
  });
  if (!res.ok) throw new Error("Erreur envoi feedback : " + res.status);
  return await res.json();
}

// Accueil (refonte UX) : 3 dernières actions d'Otis ; seule la plus récente de cette session est annulable.
export async function fetchRecentActions(sessionId) {
  const params = new URLSearchParams({ session_id: sessionId });
  const res = await fetch(`/api/v1/home/recent-actions?${params.toString()}`, { headers: getAuthHeaders() });
  if (!res.ok) throw new Error(`Dernières actions indisponibles (${res.status})`);
  return await res.json();
}
