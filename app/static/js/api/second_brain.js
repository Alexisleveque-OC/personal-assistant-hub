// Second cerveau : notes (liste, statistiques, création, modification, suppression) et import d'image.
import { state } from "../config.js";
import { getAuthHeaders } from "./http.js";

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
