// Client API HTTP fetch avec authentification par clé API
import { state } from "./config.js";

export function getAuthHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (state.apiKey) {
    headers["X-API-Key"] = state.apiKey;
  }
  return headers;
}

export async function postInteract(queryText) {
  const res = await fetch("/api/v1/interact", {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify({ query: queryText })
  });
  return res;
}

export async function postInteractAudio(audioBlob, sessionId = null) {
  const formData = new FormData();
  formData.append("audio_file", audioBlob, "recording.webm");
  if (sessionId) {
    formData.append("session_id", sessionId);
  }
  const headers = {};
  if (state.apiKey) {
    headers["X-API-Key"] = state.apiKey;
  }
  const res = await fetch("/api/v1/interact/audio", {
    method: "POST",
    headers: headers,
    body: formData
  });
  return res;
}

export async function fetchLlmStats() {
  const headers = state.apiKey ? { "x-api-key": state.apiKey } : {};
  const res = await fetch("/api/v1/llm/stats", { headers });
  if (!res.ok) return null;
  return await res.json();
}

export async function fetchWeekMeals() {
  const headers = state.apiKey ? { "x-api-key": state.apiKey } : {};
  const res = await fetch("/api/v1/meals/week", { headers });
  if (!res.ok) throw new Error("Erreur serveur " + res.status);
  return await res.json();
}

export async function fetchSportTodayData() {
  const headers = state.apiKey ? { "x-api-key": state.apiKey } : {};
  const res = await fetch("/api/v1/sport/today", { headers });
  if (!res.ok) {
    const errJson = await res.json().catch(() => null);
    const detailMsg = errJson && errJson.detail ? errJson.detail : ("Erreur serveur " + res.status);
    throw new Error(detailMsg);
  }
  return await res.json();
}

export async function fetchSportDashboardData(scale = "week") {
  const headers = state.apiKey ? { "x-api-key": state.apiKey } : {};
  const res = await fetch(`/api/v1/sport/dashboard?scale=${scale}`, { headers });
  if (!res.ok) {
    const errJson = await res.json().catch(() => null);
    const detailMsg = errJson && errJson.detail ? errJson.detail : ("Erreur serveur " + res.status);
    throw new Error(detailMsg);
  }
  return await res.json();
}

export async function fetchSportGamificationData() {
  const headers = state.apiKey ? { "x-api-key": state.apiKey } : {};
  const res = await fetch("/api/v1/sport/gamification", { headers });
  if (!res.ok) {
    const errJson = await res.json().catch(() => null);
    const detailMsg = errJson && errJson.detail ? errJson.detail : ("Erreur serveur " + res.status);
    throw new Error(detailMsg);
  }
  return await res.json();
}

export async function patchSportSession(dateStr, payload) {
  const res = await fetch(`/api/v1/sport/session/${dateStr}`, {
    method: "PATCH",
    headers: getAuthHeaders(),
    body: JSON.stringify(payload)
  });
  if (!res.ok) throw new Error("Échec de la sauvegarde");
  return await res.json();
}

export async function resetShoppingList() {
  const res = await fetch("/api/v1/meals/shopping/reset", {
    method: "POST",
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error("Erreur lors de la réinitialisation " + res.status);
  return await res.json();
}

export async function postShoppingComplete(payload) {
  const res = await fetch("/api/v1/meals/shopping/complete", {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Erreur lors de la synchronisation de fin de courses " + res.status);
  return await res.json();
}

export async function fetchSportSessionsData({ order = "desc", statut = "", type_seance = "", limit = 100, offset = 0 } = {}) {
  const headers = state.apiKey ? { "x-api-key": state.apiKey } : {};
  const params = new URLSearchParams({ order, limit: String(limit), offset: String(offset) });
  if (statut) params.append("statut", statut);
  if (type_seance) params.append("type_seance", type_seance);

  const res = await fetch(`/api/v1/sport/sessions?${params.toString()}`, { headers });
  if (!res.ok) {
    const errJson = await res.json().catch(() => null);
    const detailMsg = errJson && errJson.detail ? errJson.detail : ("Erreur serveur " + res.status);
    throw new Error(detailMsg);
  }
  return await res.json();
}

export async function fetchSportSummariesData({ order = "desc", annee = null, include_sessions = true, limit = 52, offset = 0 } = {}) {
  const headers = state.apiKey ? { "x-api-key": state.apiKey } : {};
  const params = new URLSearchParams({ order, include_sessions: String(include_sessions), limit: String(limit), offset: String(offset) });
  if (annee) params.append("annee", String(annee));

  const res = await fetch(`/api/v1/sport/summaries?${params.toString()}`, { headers });
  if (!res.ok) {
    const errJson = await res.json().catch(() => null);
    const detailMsg = errJson && errJson.detail ? errJson.detail : ("Erreur serveur " + res.status);
    throw new Error(detailMsg);
  }
  return await res.json();
}

export async function fetchSecondBrainNotes({ category = null, status = "active", search = null, limit = 50, offset = 0 } = {}) {
  const headers = state.apiKey ? { "x-api-key": state.apiKey } : {};
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (category) params.append("category", category);
  if (status) params.append("status", status);
  if (search) params.append("search", search);

  const res = await fetch(`/api/v1/second-brain/notes?${params.toString()}`, { headers });
  if (!res.ok) throw new Error("Erreur chargement second cerveau : " + res.status);
  return await res.json();
}

export async function fetchSecondBrainStats() {
  const headers = state.apiKey ? { "x-api-key": state.apiKey } : {};
  const res = await fetch("/api/v1/second-brain/stats", { headers });
  if (!res.ok) throw new Error("Erreur statistiques second cerveau : " + res.status);
  return await res.json();
}

export async function createSecondBrainNote(payload) {
  const res = await fetch("/api/v1/second-brain/notes", {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(payload)
  });
  if (!res.ok) throw new Error("Erreur création note : " + res.status);
  return await res.json();
}

export async function patchSecondBrainNote(noteId, payload) {
  const res = await fetch(`/api/v1/second-brain/notes/${noteId}`, {
    method: "PATCH",
    headers: getAuthHeaders(),
    body: JSON.stringify(payload)
  });
  if (!res.ok) throw new Error("Erreur mise à jour note : " + res.status);
  return await res.json();
}

export async function deleteSecondBrainNote(noteId) {
  const res = await fetch(`/api/v1/second-brain/notes/${noteId}`, {
    method: "DELETE",
    headers: getAuthHeaders()
  });
  if (!res.ok) throw new Error("Erreur suppression note : " + res.status);
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

export async function uploadSecondBrainImage(imageFile, { caption = null, category_override = null } = {}) {
  const formData = new FormData();
  formData.append("image", imageFile);
  if (caption) formData.append("caption", caption);
  if (category_override) formData.append("category_override", category_override);

  const headers = {};
  if (state.apiKey) {
    headers["X-API-Key"] = state.apiKey;
  }

  const res = await fetch("/api/v1/second-brain/notes/image", {
    method: "POST",
    headers: headers,
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || ("Erreur analyse image : " + res.status));
  }
  return await res.json();
}


