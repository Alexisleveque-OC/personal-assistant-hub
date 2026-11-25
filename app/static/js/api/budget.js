import { getAuthHeaders } from "./http.js";

// Écran Budget (lecture seule) : le détail renvoyé par le serveur est explicite (503 classeur indisponible,
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
