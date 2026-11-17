// Feuille « Journal & feedback » (refonte UX, étape 7 suite) : données pures, sans DOM (testées sous Node).
// Un échange avec Otis : statut, intention, date, requête, réponse, latence, modèle ; correction pour l'auto-apprentissage.
import { formatDbDate } from "./db_date.js";

function decimal(value) {
  return value.toFixed(1).replace(".", ",");
}

function formatLatency(ms) {
  if (!ms || ms <= 0) return "";
  if (ms < 10) return `${decimal(ms)} ms`;
  if (ms < 999.5) return `${Math.round(ms)} ms`;
  return `${decimal(ms / 1000)} s`;
}

export function logCard(log, now) {
  const ok = !!log.success;
  return {
    id: log.id,
    ok,
    status: ok ? "Réussi" : "Échec",
    intent: log.intent || "inconnu",
    date: formatDbDate(log.created_at, now),
    query: (log.raw_query || "").trim() || "—",
    reply: (log.spoken_response || "").trim() || (log.error_trace || "").trim() || "Aucune réponse",
    meta: [formatLatency(log.latency_ms), log.llm_model || ""].filter(Boolean).join(" · "),
  };
}

// Correction envoyée telle quelle au serveur (auto-apprentissage) ; rien à envoyer si le texte est vide.
export function feedbackPayload(text) {
  const note = String(text || "").trim();
  return note ? { feedback_type: "correction", user_note: note } : null;
}
