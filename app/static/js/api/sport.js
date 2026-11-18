// Carnet sportif : séance du jour, tableau de bord, trophées, séances (CRUD, dictée, import de capture).
import { state } from "../config.js";
import { getAuthHeaders } from "./http.js";

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
