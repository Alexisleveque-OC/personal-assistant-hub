// Feuille Second cerveau (refonte UX, maquette E-Notes) : données pures, sans DOM (testées sous Node).
import { formatDbDate } from "./db_date.js";
// Puces : Tout, Idées, À dév., Bugs toujours ; autres catégories seulement si elles ont des notes ; « Faites » à la fin.

// Catégories connues : libellé de puce, libellé de carte et teinte (classe CSS note-card__label--<tone>).
const KNOWN = {
  thought: { chip: "Idées", label: "Idée", tone: "idea" },
  dev_idea: { chip: "À dév.", label: "À développer", tone: "dev" },
  bug_report: { chip: "Bugs", label: "Bug", tone: "bug" },
  preference: { chip: "Préférences", label: "Préférence", tone: "pref" },
  task: { chip: "Tâches", label: "Tâche", tone: "task" },
};
const ALWAYS_SHOWN = ["thought", "dev_idea", "bug_report"];
const SHOWN_IF_NOTES = ["preference", "task"];
// Catégories libres déjà rencontrées (créées par Otis) : libellé de puce au pluriel.
const FREE_CHIPS = { voyage: "Voyages", vacances: "Vacances", cuisine: "Cuisine", sport_coach: "Coach sport" };


function humanize(category) {
  const text = String(category || "").replace(/_/g, " ").trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "Note";
}

function chipLabel(category) {
  if (KNOWN[category]) return KNOWN[category].chip;
  return FREE_CHIPS[category] || humanize(category);
}

function withCount(text, count) {
  return count > 0 ? `${text} · ${count}` : text;
}

export function noteChips(stats, selected = "all") {
  const counts = stats || {};
  const total = Object.values(counts).reduce((sum, n) => sum + (Number(n) || 0), 0);
  const free = Object.keys(counts)
    .filter((cat) => !KNOWN[cat] && counts[cat] > 0)
    .sort((a, b) => chipLabel(a).localeCompare(chipLabel(b), "fr"));
  const keys = [...ALWAYS_SHOWN, ...SHOWN_IF_NOTES.filter((cat) => counts[cat] > 0), ...free];
  if (selected !== "all" && selected !== "done" && !keys.includes(selected)) keys.push(selected); // puce vidée : reste visible
  return [
    { key: "all", text: withCount("Tout", total), selected: selected === "all" },
    ...keys.map((cat) => ({ key: cat, text: withCount(chipLabel(cat), counts[cat] || 0), selected: selected === cat })),
    { key: "done", text: "Faites", selected: selected === "done" },
  ];
}

export function notesQuery(key) {
  if (key === "done") return { category: null, status: "done" };
  return { category: key === "all" ? null : key, status: "active" };
}

export function noteCard(note, now) {
  const known = KNOWN[note.category];
  const done = note.status === "done";
  return {
    id: note.id,
    label: known ? known.label : humanize(note.category),
    tone: known ? known.tone : "other",
    date: formatDbDate(note.created_at, now),
    text: note.content,
    done,
    actions: done ? ["reopen"] : ["done", "task"],
  };
}

// « Annuler » d'une suppression : la note est recréée avec sa catégorie, ses mots-clés et sa date d'origine.
export function restorePayload(note) {
  return { category: note.category, content: note.content, tags: note.tags || [], created_at: note.created_at || null };
}

export function taskTitle(note) {
  return String(note.content || "").trim();
}

export function emptyText(key, search) {
  if (search) return `Aucune note ne contient « ${search} ».`;
  if (key === "done") return "Aucune note faite.";
  if (key === "all") return "Aucune note. Dites « Otis, note que… » ou écrivez ci-dessous.";
  return `Aucune note dans « ${chipLabel(key)} ».`;
}
