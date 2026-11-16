// Feuille Tâches (refonte UX, maquette E-Taches) : Google Tasks, liste « Mes tâches ».
// Sections En retard / Cette semaine / Plus tard / Sans date, puis groupes (sous-tâches Google) ; bouton ↗ = 1re URL.
// Cocher écrit tout de suite et propose « Annuler » (la tâche est rouverte, son heure recréée dans l'Agenda).
// L'ajout passe par la barre de saisie (Otis) : voir task_due_picker.js pour la date et l'heure.
import { fetchTasks, setTaskCompleted } from "../api.js";
import { showToast, showToastError } from "../toast.js";
import { taskSheet } from "../tasks_model.js";
import { el } from "./sport/dom.js";

const listContainer = document.getElementById("tasks-list-container");
const countLabel = document.getElementById("tasks-count");
const SVG_NS = "http://www.w3.org/2000/svg";

let openTasks = [];

export function initTasksView() {
  // Rien à brancher au démarrage : la feuille se remplit à son ouverture (loadTasks).
}

function note(text, className = "muted") {
  return el("p", `shopping-note ${className}`, text);
}

function todayIso() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

export async function loadTasks() {
  if (!listContainer) return;
  listContainer.replaceChildren(note("Chargement des tâches…"));
  try {
    const view = await fetchTasks();
    openTasks = view.taches || [];
    renderTasks();
  } catch (err) {
    if (countLabel) countLabel.textContent = "";
    listContainer.replaceChildren(note(err.message || "Impossible de charger les tâches.", "shopping-note--error"));
  }
}

function linkIcon() {
  const svg = document.createElementNS(SVG_NS, "svg");
  for (const [name, value] of Object.entries({
    viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "2.2",
    "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true",
  })) svg.setAttribute(name, value);
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", "M14 4h6v6M20 4l-9 9M18 14v6H4V6h6");
  svg.append(path);
  return svg;
}

function taskRow(item) {
  const row = el("label", "list-row");
  const box = el("input", "check");
  box.type = "checkbox";
  box.addEventListener("change", () => completeTask(item, box));
  row.append(box, el("span", "list-row__text", item.titre));
  if (item.badge) row.append(el("span", `badge badge--${item.badge.tone}`, item.badge.text));
  if (item.link) {
    const link = el("a", "task-link");
    link.href = item.link;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.setAttribute("aria-label", "Ouvrir le lien");
    link.append(linkIcon());
    row.append(link);
  }
  return row;
}

function block(title, items, accent = false) {
  const card = el("div", "list-group");
  card.append(...items.map(taskRow));
  return [el("span", `section-label${accent ? " section-label--accent" : ""}`, title), card];
}

function renderTasks() {
  const sheet = taskSheet(openTasks, todayIso());
  if (countLabel) countLabel.textContent = sheet.count ? String(sheet.count) : "";
  if (!sheet.count) {
    listContainer.replaceChildren(note("Aucune tâche en cours 🎉"));
    return;
  }
  listContainer.replaceChildren(
    ...sheet.sections.flatMap((s) => block(s.title, s.items, s.key === "week")),
    ...sheet.groups.flatMap((g) => block(g.title, g.items)),
  );
}

async function completeTask(item, box) {
  box.disabled = true; // écriture en cours : pas de double envoi
  try {
    await setTaskCompleted(item.id, true);
  } catch (err) {
    box.checked = false;
    box.disabled = false;
    showToastError(err.message, "Tâche non cochée");
    return;
  }
  openTasks = openTasks.filter((t) => t.id !== item.id);
  renderTasks();
  showToast(`« ${item.titre} » est cochée.`, "success", {
    title: "Tâche terminée",
    duration: 6000,
    action: { label: "Annuler", onClick: () => reopenTask(item) },
  });
}

async function reopenTask(item) {
  try {
    await setTaskCompleted(item.id, false, { heure: item.heure, rappel_minutes_avant: item.rappel_minutes_avant });
  } catch (err) {
    showToastError(err.message, "Tâche non rouverte");
    return;
  }
  await loadTasks();
}
