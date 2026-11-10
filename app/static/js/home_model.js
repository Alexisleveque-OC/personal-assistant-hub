// Accueil (refonte UX) : contenu des bulles et des « Dernières actions », à partir des réponses de l'API.
// Sans import ni DOM (testé sous Node) ; le rendu est dans views/home_view.js.

const DAYS_SHORT = ["dim.", "lun.", "mar.", "mer.", "jeu.", "ven.", "sam."];
const MONTHS_SHORT = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];

const capitalize = (text) => text.charAt(0).toUpperCase() + text.slice(1);

// « 7,01 » / « 12 » (au plus deux décimales, virgule française)
function formatKm(km) {
  return String(Math.round(km * 100) / 100).replace(".", ",");
}

// 🛒 Articles de « Cette semaine » restant à prendre (cochés dans le classeur ou sur ce téléphone exclus).
export function shoppingSummary(data, locallyChecked = []) {
  const checked = new Set(locallyChecked);
  const left = ((data && data.current_week_items) || []).filter((i) => !i.checked && !checked.has(i.name));
  if (!left.length) return { count: 0, value: "Rien à acheter", foot: "" };
  const firsts = left.slice(0, 3).map((i) => i.name).join(", ");
  return {
    count: left.length,
    value: `${left.length} article${left.length > 1 ? "s" : ""}`,
    foot: left.length > 3 ? `${firsts}…` : firsts,
  };
}

// « Jeu. 12 nov. » à partir d'une date ISO (AAAA-MM-JJ, jour local)
export function formatDueDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  const day = new Date(y, m - 1, d);
  return `${capitalize(DAYS_SHORT[day.getDay()])} ${d} ${MONTHS_SHORT[m - 1]}`;
}

// 📌 Tâche datée la plus proche (retards compris), sinon la première sans date.
export function nextTask(taches) {
  const list = taches || [];
  const dated = list.filter((t) => t.echeance).sort((a, b) => a.echeance.localeCompare(b.echeance));
  if (dated.length) return { value: dated[0].titre, foot: formatDueDate(dated[0].echeance) };
  if (list.length) return { value: list[0].titre, foot: "Sans date" };
  return { value: "Aucune tâche", foot: "" };
}

// 🍲 Dîner du jour en grand, déjeuner en petit (planning de la semaine, entrée `is_today`).
export function tonightMeal(weekPlan) {
  const today = (weekPlan || []).find((d) => d.is_today) || {};
  return {
    value: today.dinner || "Rien de prévu",
    foot: `Midi : ${today.lunch || "rien de prévu"}`,
  };
}

// 🏃 Séance du jour, sinon « Repos 😌 » ; ligne du bas = message du coach (coupé à 2 lignes par le CSS).
export function sportOfTheDay(today) {
  const session = ((today && today.seances) || [])[0];
  const coach = (today && today.coach_tip && today.coach_tip.message) || "";
  if (!session) return { value: "Repos 😌", foot: coach };
  const km = session.distance_km ? ` · ${formatKm(session.distance_km)} km` : "";
  return { value: `${session.type_seance}${km}`, foot: coach };
}

// Heure d'une action : « 18:36 » aujourd'hui, « hier », sinon « jeu. 5 ».
export function actionTime(iso, now = new Date()) {
  if (!iso) return "";
  const at = new Date(iso);
  const sameDay = (a, b) => a.toDateString() === b.toDateString();
  if (sameDay(at, now)) {
    return `${String(at.getHours()).padStart(2, "0")}:${String(at.getMinutes()).padStart(2, "0")}`;
  }
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (sameDay(at, yesterday)) return "hier";
  return `${DAYS_SHORT[at.getDay()]} ${at.getDate()}`;
}

// Dernière réponse d'Otis dans la conversation sauvegardée sur ce téléphone.
export function lastAssistantReply(history) {
  const last = [...(history || [])].reverse().find((m) => m.role === "assistant" && m.text);
  return last ? last.text : null;
}
