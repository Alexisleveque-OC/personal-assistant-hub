// Feuille Tâches (refonte UX, maquette E-Taches) : sections par échéance, groupes de sous-tâches, pastilles, lien.
// Sans import ni DOM (testé sous Node) ; le rendu est dans views/tasks_view.js.
// Dates ISO (AAAA-MM-JJ) traitées en UTC pour que le fuseau du téléphone ne décale jamais un jour.

const DAYS_SHORT = ["dim.", "lun.", "mar.", "mer.", "jeu.", "ven.", "sam."];
const DAYS_LONG = ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"];
const MONTHS_SHORT = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
const MONTHS_LONG = [
  "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre",
];

const SECTIONS = [
  { key: "late", title: "En retard", tone: "danger" },
  { key: "week", title: "Cette semaine", tone: "accent" },
  { key: "later", title: "Plus tard", tone: "muted" },
  { key: "none", title: "Sans date", tone: null },
];

function utcDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

function isoOf(date) {
  return date.toISOString().slice(0, 10);
}

// Dimanche de la semaine (lundi → dimanche) qui contient `todayIso`.
function endOfWeek(todayIso) {
  const today = utcDate(todayIso);
  const daysToSunday = (7 - today.getUTCDay()) % 7;
  return isoOf(new Date(today.getTime() + daysToSunday * 86400000));
}

function sectionKey(echeance, todayIso, sundayIso) {
  if (!echeance) return "none";
  if (echeance < todayIso) return "late";
  if (echeance <= sundayIso) return "week";
  return "later";
}

function badgeText(key, echeance, heure) {
  const day = utcDate(echeance);
  const label = key === "week"
    ? `${DAYS_SHORT[day.getUTCDay()]} ${day.getUTCDate()}`
    : `${day.getUTCDate()} ${MONTHS_SHORT[day.getUTCMonth()]}`;
  return heure ? `${label} · ${heure}` : label;
}

// Première adresse http(s) des notes, sinon du titre (ponctuation finale exclue) ; aucune autre forme de lien.
export function firstUrl(task) {
  for (const text of [task && task.notes, task && task.titre]) {
    const match = /https?:\/\/[^\s<>"']+/i.exec(text || "");
    if (match) return match[0].replace(/[.,;:!?)\]]+$/, "");
  }
  return null;
}

// Tâches affichées en lignes : une tâche parente d'au moins une sous-tâche ouverte devient un titre de groupe.
export function openRows(taches) {
  const list = taches || [];
  const parents = new Set(list.filter((t) => t.parent).map((t) => t.parent));
  return list.filter((t) => !parents.has(t.id));
}

function row(task, todayIso, sundayIso) {
  const key = sectionKey(task.echeance, todayIso, sundayIso);
  const tone = SECTIONS.find((s) => s.key === key).tone;
  return {
    id: task.id,
    titre: task.titre,
    badge: task.echeance ? { text: badgeText(key, task.echeance, task.heure), tone } : null,
    link: firstUrl(task),
    heure: task.heure || null,
    rappel_minutes_avant: task.rappel_minutes_avant ?? null,
  };
}

const byDueThenHour = (a, b) =>
  (a.echeance || "").localeCompare(b.echeance || "") || (a.heure || "").localeCompare(b.heure || "");

// Sections En retard / Cette semaine / Plus tard / Sans date (vides omises), puis groupes de sous-tâches.
export function taskSheet(taches, todayIso) {
  const list = taches || [];
  const sundayIso = endOfWeek(todayIso);
  const ids = new Set(list.map((t) => t.id));
  const rows = openRows(list);
  const isGrouped = (t) => t.parent && ids.has(t.parent);

  const sections = SECTIONS.map((s) => ({
    key: s.key,
    title: s.title,
    items: rows
      .filter((t) => !isGrouped(t) && sectionKey(t.echeance, todayIso, sundayIso) === s.key)
      .sort(s.key === "none" ? () => 0 : byDueThenHour)
      .map((t) => row(t, todayIso, sundayIso)),
  })).filter((s) => s.items.length);

  const groups = list
    .filter((t) => !rows.includes(t)) // tâches parentes
    .map((parent) => ({
      id: parent.id,
      title: parent.titre,
      items: list.filter((t) => t.parent === parent.id).map((t) => row(t, todayIso, sundayIso)),
    }));

  return { count: rows.length, sections, groups };
}

// Pastille de la barre de saisie : « jeu. 19 nov. » ou « jeu. 19 nov. · 14:30 ».
export function dueChipLabel(due) {
  const day = utcDate(due.date);
  const label = `${DAYS_SHORT[day.getUTCDay()]} ${day.getUTCDate()} ${MONTHS_SHORT[day.getUTCMonth()]}`;
  return due.time ? `${label} · ${due.time}` : label;
}

// Message envoyé à Otis : la date (et l'heure) choisies au calendrier sont jointes en clair.
export function withDue(text, due) {
  if (!due || !due.date) return text;
  const day = utcDate(due.date);
  const when = `${DAYS_LONG[day.getUTCDay()]} ${day.getUTCDate()} ${MONTHS_LONG[day.getUTCMonth()]} ${day.getUTCFullYear()}`;
  return `${text} — échéance le ${when}${due.time ? ` à ${due.time}` : ""}`;
}
