// Feuille « Réglages & voix » (refonte UX, étape 7 suite) : données pures, sans import ni DOM (testées sous Node).
// Encart « Modèle & quotas Gemini » : compteurs du serveur (GET /api/v1/llm/stats) mis en forme.

const UNAVAILABLE = {
  model: "Indisponible", requests: "—", remaining: "—", latency: "—", badge: { text: "Indisponible", tone: "muted" },
};

function quotaBadge(data) {
  if (data.quota_exceeded) return { text: "Quota atteint", tone: "danger" };
  if (data.remaining_daily_requests < 100) return { text: "Attention", tone: "warn" };
  return { text: "Actif", tone: "ok" };
}

export function llmStatsView(data) {
  if (!data) return UNAVAILABLE;
  return {
    model: data.model || "Indisponible",
    requests: `${data.daily_requests} / ${data.max_daily_requests}`,
    remaining: `${data.remaining_daily_requests} restantes`,
    latency: data.last_latency_ms ? `${Math.round(data.last_latency_ms)} ms` : "Aucune requête",
    badge: quotaBadge(data),
  };
}
