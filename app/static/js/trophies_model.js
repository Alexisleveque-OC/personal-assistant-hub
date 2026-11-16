// Écran Trophées (refonte UX, maquette E-Trophees) : logique d'affichage pure, sans import ni DOM (testée sous Node).
// Données : GET /api/v1/sport/gamification (SportGamificationSummary).

const MONTHS_SHORT = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
const DAY_MS = 86400000;

// Onglets (décision du 16/11) : les 8 catégories du serveur regroupées en 4.
export const TROPHY_TABS = [
  { key: "seance", label: "⚡ En une séance", categories: ["mono_session"] },
  { key: "cumuls", label: "📈 Cumuls", categories: ["distance", "denivele", "temps", "regularite"] },
  { key: "pop", label: "🧙 Pop‑culture", categories: ["pop_culture"] },
  { key: "secrets", label: "🕵️ Secrets & absurdes", categories: ["secret", "absurde"] },
];

// Paliers rangés derrière « Voir les légendaires 👑🪐 ».
const LEGENDARY_TIERS = ["diamant", "mythique"];
const JUST_UNLOCKED_DAYS = 7;

const parseIso = (iso) => new Date(`${iso}T00:00:00Z`);

// Nombre à la française, `decimals` décimales au plus (zéros finaux retirés) : 10,3 · 1 000 · 384 400.
function frNumber(value, decimals = 1) {
  const [whole, frac] = Math.abs(Number(value)).toFixed(decimals).split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  const trimmed = (frac || "").replace(/0+$/, "");
  return `${Number(value) < 0 ? "-" : ""}${grouped}${trimmed ? `,${trimmed}` : ""}`;
}

function shortDate(iso) {
  const day = parseIso(iso);
  return `${day.getUTCDate()} ${MONTHS_SHORT[day.getUTCMonth()]}`;
}

// Débloqué il y a 7 jours au plus (date de la séance qui a fait basculer le trophée).
export function isJustUnlocked(unlockedAt, todayIso) {
  if (!unlockedAt) return false;
  const days = Math.round((parseIso(todayIso) - parseIso(unlockedAt)) / DAY_MS);
  return days >= 0 && days <= JUST_UNLOCKED_DAYS;
}

function progressLabel(badge) {
  const pct = badge.progress_pct;
  if (pct >= 90) return `${pct} % · encore un effort !`;
  const unit = badge.unit ? ` ${badge.unit}` : "";
  return `${frNumber(badge.current_value)} / ${frNumber(badge.target_value)}${unit} · ${pct} %`;
}

function trophyCard(badge, todayIso) {
  const unlocked = Boolean(badge.is_unlocked);
  // Progression seulement pour un objectif chiffré visible (les secrets gardent leur énigme).
  const showsProgress = !unlocked && !badge.is_secret && Boolean(badge.target_value);
  const tier = badge.rarity || "bronze";
  return {
    id: badge.id,
    emoji: badge.icon,
    name: badge.title,
    tier,
    tierLabel: tier.toUpperCase(),
    unlocked,
    justUnlocked: unlocked && isJustUnlocked(badge.unlocked_at, todayIso),
    desc: showsProgress ? null : badge.description,
    doneLabel: unlocked ? `Débloqué ✓${badge.unlocked_at ? ` · ${shortDate(badge.unlocked_at)}` : ""}` : null,
    progressPct: showsProgress ? badge.progress_pct : null,
    progressLabel: showsProgress ? progressLabel(badge) : null,
  };
}

// Débloqués d'abord (les plus récents en tête), puis progression décroissante.
function compareBadges(a, b) {
  if (a.is_unlocked !== b.is_unlocked) return a.is_unlocked ? -1 : 1;
  if (a.is_unlocked) return (b.unlocked_at || "").localeCompare(a.unlocked_at || "");
  return (b.progress_pct || 0) - (a.progress_pct || 0);
}

export function trophiesForTab(badges, tabKey, todayIso) {
  const tab = TROPHY_TABS.find((t) => t.key === tabKey) || TROPHY_TABS[0];
  const cards = (badges || [])
    .filter((b) => tab.categories.includes(b.category))
    .sort(compareBadges)
    .map((b) => trophyCard(b, todayIso));
  return {
    main: cards.filter((c) => !LEGENDARY_TIERS.includes(c.tier)),
    legendary: cards.filter((c) => LEGENDARY_TIERS.includes(c.tier)),
  };
}

export function trophyOverview(data) {
  const unlocked = data.unlocked_count || 0;
  const total = data.total_badges || 0;
  return { unlocked, total, pct: total ? Math.round((unlocked / total) * 100) : 0 };
}

// Palier imminent 🎯 : premier palier du serveur, jauge = progression du trophée visé.
export function imminentMilestone(data) {
  const first = (data.imminent_milestones || [])[0];
  if (!first) return null;
  const badge = (data.badges || []).find((b) => b.id === first.badge_id);
  return { message: first.message, pct: badge ? badge.progress_pct : 0 };
}

// « Derniers exploits » : annonces du serveur, émoji de tête détaché du texte.
export function exploits(announcements) {
  return (announcements || []).map((text) => {
    const match = text.match(/^(\p{Extended_Pictographic}️?)\s*(.*)$/u);
    return match ? { emoji: match[1], text: match[2] } : { emoji: "🏅", text };
  });
}

const RECORDS = {
  longest_run: { emoji: "📏", label: "plus longue", value: (v) => `${frNumber(v, 2)} km` },
  max_elevation: { emoji: "🏔️", label: "plus gros D+", value: (v) => `${frNumber(v)} m` },
  best_pace: {
    emoji: "🚀",
    label: "allure ≥3 km",
    value: (v) => `${Math.floor(v / 60)}:${String(Math.round(v % 60)).padStart(2, "0")}`,
  },
};

export function recordTile(record) {
  const known = RECORDS[record.record_type];
  if (!known) return { emoji: "🏅", value: record.formatted_value, label: record.title };
  const label = record.date ? `${known.label} · ${shortDate(record.date)}` : known.label;
  return { emoji: known.emoji, value: known.value(record.value), label };
}

// Équivalences insolites : chiffre-clé + détail du serveur, sinon titre + phrase.
export function equivalence(fact) {
  return { emoji: fact.icon, headline: fact.headline || fact.title, detail: fact.detail || fact.text };
}
