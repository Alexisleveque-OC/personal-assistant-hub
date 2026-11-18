import { getAuthHeaders } from "./http.js";

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
