import { getAuthHeaders } from "./http.js";

// Écran Budget : le détail renvoyé par le serveur est explicite (503 classeur indisponible,
// 502 structure du classeur modifiée ou lecture refusée par Google).
export async function fetchBudgetOverview() {
  const res = await fetch("/api/v1/budget/overview", { method: "GET", headers: getAuthHeaders() });
  if (!res.ok) {
    const errJson = await res.json().catch(() => null);
    const detail = errJson && errJson.detail;
    throw new Error(typeof detail === "string" ? detail : `Erreur de chargement du budget (${res.status})`);
  }
  return await res.json();
}

// Formulaires (étapes 7b, 7c) : 201 avec `message` et `action_id` (annulable via « Dernières actions »),
// 422 saisie refusée (catégorie, somme des parts…, rien n'est écrit), 503 / 502 comme la lecture.
async function postBudgetForm(path, payload) {
  const res = await fetch(`/api/v1/budget/${path}`, {
    method: "POST", headers: getAuthHeaders(), body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errJson = await res.json().catch(() => null);
    const detail = errJson && errJson.detail;
    throw new Error(typeof detail === "string" ? detail : `Saisie non enregistrée (${res.status})`);
  }
  return await res.json();
}

export const addBudgetEntry = (payload) => postBudgetForm("entries", payload);
export const addBudgetInstallment = (payload) => postBudgetForm("installments", payload);
export const addBudgetSplitExpense = (payload) => postBudgetForm("split-expenses", payload);

// Import Swile (étape 8) : captures → relecture (rien n'est écrit) ; `referenceDate` = jour local (dates relatives).
// 422 rien de lisible (raisons citées), 503 Gemini ou classeur indisponible, 502 classeur.
export async function analyzeSwileCaptures(files, referenceDate) {
  const body = new FormData();
  files.forEach((file) => body.append("files", file));
  const headers = getAuthHeaders();
  delete headers["Content-Type"]; // FormData fixe lui-même le type multipart et sa frontière
  const res = await fetch(`/api/v1/budget/swile/analyze?reference_date=${encodeURIComponent(referenceDate)}`, {
    method: "POST", headers, body,
  });
  if (!res.ok) {
    const errJson = await res.json().catch(() => null);
    const detail = errJson && errJson.detail;
    throw new Error(typeof detail === "string" ? detail : `Lecture des captures impossible (${res.status})`);
  }
  return await res.json();
}

export const importSwileLines = (payload) => postBudgetForm("swile/import", payload);
