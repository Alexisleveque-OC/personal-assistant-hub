// Repas et courses : planning de la semaine, liste de courses, suppression / rétablissement d'un plat.
import { getAuthHeaders } from "./http.js";

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
