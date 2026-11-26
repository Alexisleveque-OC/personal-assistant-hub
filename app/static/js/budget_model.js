// Écran Budget (Phase 10, étape 7a) : données pures, sans import ni DOM (testées sous Node).
// Entrée : GET /api/v1/budget/overview. Graphique Dépenses vs Revenus par mois, épargné du mois actif, groupes de
// `Gestion` avec, par catégorie, le reste total (rouge si négatif) et le suivi du mois (barre de progression).
// Le groupe Revenus n'est pas envoyé : les revenus ne figurent que dans le graphique (décision du 26/11).

const MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin",
  "juillet", "août", "septembre", "octobre", "novembre", "décembre"];
const MONTH_INITIALS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
const NBSP = " "; // avant « € »
const NNBSP = " "; // séparateur des milliers (comme Intl fr-FR)
const MINUS = "−";

function groupThousands(n) {
  return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, NNBSP);
}

// « 923,15 € », « 1 000 € » (centimes seulement s'il y en a), « −100,69 € ».
export function formatEuros(amount) {
  const cents = Math.round(Number(amount) * 100);
  if (cents === 0) return `0${NBSP}€`;
  const abs = Math.abs(cents);
  const decimals = abs % 100 ? `,${String(abs % 100).padStart(2, "0")}` : "";
  return `${cents < 0 ? MINUS : ""}${groupThousands(Math.floor(abs / 100))}${decimals}${NBSP}€`;
}

// Étiquette courte d'une barre : « 203 », « 4,8k ».
function compactEuros(amount) {
  const sign = amount < 0 ? MINUS : "";
  const abs = Math.abs(amount);
  if (abs < 1000) return `${sign}${Math.round(abs)}`;
  return `${sign}${(Math.round(abs / 100) / 10).toString().replace(".", ",")}k`;
}

function toneOf(amount) {
  return Math.round(amount * 100) < 0 ? "danger" : "default";
}

function chartOf(series, active) {
  const max = Math.max(0, ...series.flatMap((p) => [p.expenses, p.income]));
  const bar = (amount) => ({ value: compactEuros(amount), pct: max > 0 ? Math.round((Math.max(amount, 0) / max) * 100) : 0 });
  return series.map((p) => ({
    axis: MONTH_INITIALS[p.month.month - 1],
    current: p.month.year === active.year && p.month.month === active.month,
    expenses: bar(p.expenses),
    income: bar(p.income),
    label: `${MONTHS[p.month.month - 1]} : dépenses ${formatEuros(p.expenses)}, revenus ${formatEuros(p.income)}`,
  }));
}

function categoryOf(c) {
  const spent = c.month_spent;
  const budget = c.month_budget;
  let pct = 0;
  if (budget > 0) pct = Math.min(100, Math.round((spent / budget) * 100));
  else if (spent > 0) pct = 100;
  return {
    name: c.name,
    remaining: { text: formatEuros(c.total_remaining), tone: toneOf(c.total_remaining) },
    detail: `ce mois : dépensé ${formatEuros(spent)} / budget ${formatEuros(budget)}`,
    pct: Math.max(pct, 0),
    over: Math.round(spent * 100) > Math.round(budget * 100),
  };
}

export function budgetSheet(overview) {
  const active = overview.active_month;
  return {
    title: `${MONTHS[active.month - 1]} ${active.year}`,
    saved: { text: formatEuros(overview.saved), tone: Math.round(overview.saved * 100) < 0 ? "danger" : "ok" },
    chart: chartOf(overview.series || [], active),
    groups: (overview.groups || []).map((g) => ({
      name: g.name,
      total: { text: formatEuros(g.total_remaining), tone: toneOf(g.total_remaining) },
      categories: g.categories.map(categoryOf),
    })),
  };
}
