// Socle du client HTTP : en-têtes d'authentification (clé API) et contexte d'interaction envoyé à Otis.
import { state } from "../config.js";

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
