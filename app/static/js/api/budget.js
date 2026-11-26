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
