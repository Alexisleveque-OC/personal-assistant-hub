// Client API HTTP fetch avec authentification par clé API
import { state, getActiveSessionId } from "./config.js";

export function getAuthHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (state.apiKey) {
    headers["X-API-Key"] = state.apiKey;
  }
  return headers;
}

// Feuille ouverte (« courses », « sport »…) transmise à Otis pour lever les ambiguïtés (refonte UX).
// Un message rejoué par la file hors-ligne part avec la feuille ouverte au moment du rejeu.
// `ui_session_id` : séance ouverte dans le détail Sport, toujours envoyé (null ailleurs) car le serveur garde le contexte.
export function currentInteractionContext() {
  return { ui_context: state.uiContext || "accueil", ui_session_id: state.uiSessionId ?? null };
}

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

// Planning samedi → vendredi (onglet annuel « repas AAAA ») lu directement, avec les ingrédients des recettes.
// `offset` : semaines après (+) ou avant (-) la semaine en cours.
export async function fetchWeekMeals(offset = 0) {
  const res = await fetch(`/api/v1/meals/week?offset=${encodeURIComponent(offset)}`, { headers: getAuthHeaders() });
  if (!res.ok) {
    const errJson = await res.json().catch(() => null);
    throw new Error((errJson && errJson.detail) || `Planning des repas indisponible (${res.status})`);
  }
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

export async function fetchSportDashboardData(scale = "week", refDate = null) {
  const headers = state.apiKey ? { "x-api-key": state.apiKey } : {};
  // refDate (YYYY-MM-DD) : un jour de la période voulue ; absent = période en cours
  const params = new URLSearchParams({ scale });
  if (refDate) params.append("date", refDate);
  const res = await fetch(`/api/v1/sport/dashboard?${params.toString()}`, { headers });
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

export async function patchSportSessionById(sessionId, payload) {
  const res = await fetch(`/api/v1/sport/session/id/${sessionId}`, {
    method: "PATCH",
    headers: getAuthHeaders(),
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    const errJson = await res.json().catch(() => null);
    const detailMsg = errJson && errJson.detail ? errJson.detail : ("Échec de la modification (" + res.status + ")");
    throw new Error(detailMsg);
  }
  return await res.json();
}

export async function deleteSportSession(sessionId) {
  const res = await fetch(`/api/v1/sport/session/${sessionId}`, {
    method: "DELETE",
    headers: getAuthHeaders()
  });
  if (!res.ok) {
    const errJson = await res.json().catch(() => null);
    const detailMsg = errJson && errJson.detail ? errJson.detail : ("Échec de la suppression (" + res.status + ")");
    throw new Error(detailMsg);
  }
  return await res.json();
}

export async function createSportSession(payload) {
  const res = await fetch("/api/v1/sport/session", {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    const errJson = await res.json().catch(() => null);
    const detailMsg = errJson && errJson.detail ? errJson.detail : ("Échec de la création (" + res.status + ")");
    throw new Error(detailMsg);
  }
  return await res.json();
}

// « Dicte ta séance » : la dictée est analysée sans rien enregistrer ; renvoie { transcription, draft, dropped }.
export async function postSportSessionDraft(audioBlob) {
  const mime = (audioBlob && audioBlob.type ? audioBlob.type : "").toLowerCase();
  const filename = mime.includes("mp4") ? "dictee.mp4" : mime.includes("ogg") ? "dictee.ogg" : "dictee.webm";
  const formData = new FormData();
  formData.append("audio_file", audioBlob, filename);
  const res = await fetch("/api/v1/sport/session/draft", {
    method: "POST",
    headers: state.apiKey ? { "X-API-Key": state.apiKey } : {},
    body: formData,
  });
  if (!res.ok) {
    const errJson = await res.json().catch(() => null);
    throw new Error(errJson && errJson.detail ? errJson.detail : `Dictée non analysée (erreur ${res.status})`);
  }
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

// date_from / date_to (AAAA-MM-JJ, inclus) : séances d'une période (ex. la semaine affichée).
export async function fetchSportSessionsData({
  order = "desc", statut = "", type_seance = "", limit = 100, offset = 0, date_from = "", date_to = "",
} = {}) {
  const headers = state.apiKey ? { "x-api-key": state.apiKey } : {};
  const params = new URLSearchParams({ order, limit: String(limit), offset: String(offset) });
  if (statut) params.append("statut", statut);
  if (type_seance) params.append("type_seance", type_seance);
  if (date_from) params.append("date_from", date_from);
  if (date_to) params.append("date_to", date_to);

  const res = await fetch(`/api/v1/sport/sessions?${params.toString()}`, { headers });
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

// Notes du Second cerveau : le message d'erreur du serveur (detail) est remonté tel quel.
async function brainRequest(url, init, fallback) {
  const res = await fetch(url, { ...init, headers: getAuthHeaders() });
  if (!res.ok) {
    const errJson = await res.json().catch(() => null);
    throw new Error((errJson && typeof errJson.detail === "string" && errJson.detail) || `${fallback} (${res.status})`);
  }
  return await res.json();
}

export async function createSecondBrainNote(payload) {
  return brainRequest("/api/v1/second-brain/notes", { method: "POST", body: JSON.stringify(payload) }, "Note non enregistrée");
}

export async function patchSecondBrainNote(noteId, payload) {
  return brainRequest(`/api/v1/second-brain/notes/${noteId}`, {
    method: "PATCH", body: JSON.stringify(payload),
  }, "Note non mise à jour");
}

export async function deleteSecondBrainNote(noteId) {
  return brainRequest(`/api/v1/second-brain/notes/${noteId}`, { method: "DELETE" }, "Note non supprimée");
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

export async function importSportScreenshot(imageFile, { referenceDate = null } = {}) {
  const formData = new FormData();
  formData.append("file", imageFile);

  const headers = {};
  if (state.apiKey) {
    headers["X-API-Key"] = state.apiKey;
  }

  // referenceDate (YYYY-MM-DD) : date saisie par l'utilisateur quand la capture n'en contient pas
  const url = referenceDate
    ? `/api/v1/sport/import-screenshot?reference_date=${encodeURIComponent(referenceDate)}`
    : "/api/v1/sport/import-screenshot";

  const res = await fetch(url, {
    method: "POST",
    headers: headers,
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const error = new Error(err.detail || ("Erreur lors de l'import de la capture : " + res.status));
    error.status = res.status;
    error.code = res.headers.get("X-Error-Code");
    throw error;
  }
  return await res.json();
}




// Onglet Tâches (Google Tasks, liste « Mes tâches ») : le détail renvoyé par le serveur est explicite (503 non configuré, 502 erreur Google).
async function tasksRequest(url, options, fallbackMessage) {
  const res = await fetch(url, { headers: getAuthHeaders(), ...options });
  if (!res.ok) {
    const errJson = await res.json().catch(() => null);
    const detail = errJson && errJson.detail;
    throw new Error(typeof detail === "string" ? detail : `${fallbackMessage} (${res.status})`);
  }
  return res.status === 204 ? null : await res.json(); // 204 : suppression, sans corps
}

// Accueil (refonte UX) : 3 dernières actions d'Otis ; seule la plus récente de cette session est annulable.
export async function fetchRecentActions(sessionId) {
  const params = new URLSearchParams({ session_id: sessionId });
  const res = await fetch(`/api/v1/home/recent-actions?${params.toString()}`, { headers: getAuthHeaders() });
  if (!res.ok) throw new Error(`Dernières actions indisponibles (${res.status})`);
  return await res.json();
}

// Liste de courses lue directement (sans question à Otis, donc sans écrire dans le journal).
export async function fetchShoppingData() {
  const res = await fetch("/api/v1/meals/shopping", { headers: getAuthHeaders() });
  if (!res.ok) {
    const errJson = await res.json().catch(() => null);
    throw new Error((errJson && errJson.detail) || `Liste de courses indisponible (${res.status})`);
  }
  return await res.json();
}

// Feuille Repas : « Supprimer » vide le créneau tout de suite ; « Annuler » réécrit le plat retiré.
async function mealPlanRequest(dateIso, moment, init, fallback) {
  const res = await fetch(`/api/v1/meals/plan/${encodeURIComponent(dateIso)}/${encodeURIComponent(moment)}`, {
    ...init, headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
  });
  if (!res.ok) {
    const errJson = await res.json().catch(() => null);
    throw new Error((errJson && typeof errJson.detail === "string" && errJson.detail) || `${fallback} (${res.status})`);
  }
  return await res.json();
}

export async function deleteMeal(dateIso, moment) {
  return mealPlanRequest(dateIso, moment, { method: "DELETE" }, "Suppression du plat impossible");
}

export async function restoreMeal(dateIso, moment, plat) {
  return mealPlanRequest(dateIso, moment, { method: "PUT", body: JSON.stringify({ plat }) }, "Plat non rétabli");
}

export async function fetchTasks() {
  return tasksRequest("/api/v1/tasks", { method: "GET" }, "Erreur de chargement des tâches");
}

export async function createTask(titre, echeance = null) {
  return tasksRequest("/api/v1/tasks", {
    method: "POST",
    body: JSON.stringify({ titre, echeance: echeance || null }),
  }, "Échec de l'ajout de la tâche");
}

// « Annuler » de « En faire une tâche » (Second cerveau) : la tâche créée est supprimée (et son événement Agenda).
export async function deleteTask(taskId) {
  return tasksRequest(`/api/v1/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" }, "Échec de la suppression de la tâche");
}

// `reopen` (« Annuler ») : heure et rappel de la tâche, pour recréer son événement Agenda supprimé à la coche.
export async function setTaskCompleted(taskId, terminee, reopen = {}) {
  const body = { terminee };
  if (!terminee && reopen.heure) body.heure = reopen.heure;
  if (!terminee && reopen.heure && reopen.rappel_minutes_avant) body.rappel_minutes_avant = reopen.rappel_minutes_avant;
  return tasksRequest(`/api/v1/tasks/${encodeURIComponent(taskId)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  }, terminee ? "Échec du cochage de la tâche" : "Échec de la réouverture de la tâche");
}
