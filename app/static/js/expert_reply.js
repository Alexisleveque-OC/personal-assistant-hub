// Réponse de l'expert Claude (Phase 6.10) : une réponse courte peut être approfondie par un lien discret.
export const DEEPEN_QUERY = "Approfondis";

export function canDeepen(response) {
  const data = response && response.data;
  return Boolean(data && data.level === "expert" && data.expert && data.expert.reason !== "approfondir");
}

export function deepenContext() {
  return { expert_detailed: true };
}
