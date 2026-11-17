// Feuille Second cerveau (refonte UX, maquette E-Notes ; décisions du 17/11).
// Puces de catégorie (Tout, Idées, À dév., Bugs, autres si non vides, Faites), cartes de notes.
// « Fait », « En faire une tâche » (tâche Google sans date + note faite) et « Supprimer » (menu ⋯) écrivent tout de suite
// et proposent « Annuler ». La loupe ouvre la recherche ; l'ajout passe par la barre de saisie (Otis) et sa photo.
import {
  createSecondBrainNote,
  createTask,
  deleteSecondBrainNote,
  deleteTask,
  fetchSecondBrainNotes,
  fetchSecondBrainStats,
  patchSecondBrainNote,
  uploadSecondBrainImage,
} from "../api.js";
import { emptyText, noteCard, noteChips, notesQuery, restorePayload, taskTitle } from "../notes_model.js";
import { showToast, showToastError, showToastSuccess } from "../toast.js";
import { button, el } from "./sport/dom.js";

const sheet = document.getElementById("view-second-brain");
const listContainer = document.getElementById("second-brain-list");
const chipsContainer = document.getElementById("brain-chips");
const searchButton = document.getElementById("btn-brain-search");
const searchBox = document.getElementById("brain-search");
const searchInput = document.getElementById("brain-search-input");
const SVG_NS = "http://www.w3.org/2000/svg";

let selected = "all";
let search = "";
let stats = {};
let notes = [];

function isOpen() {
  return !!sheet && sheet.getAttribute("aria-hidden") === "false";
}

function message(text, className = "muted") {
  return el("p", `shopping-note ${className}`, text);
}

// Chaque ouverture depuis le menu repart de « Tout », sans recherche.
export function resetSecondBrainFilters() {
  selected = "all";
  setSearchOpen(false);
}

export async function loadSecondBrain() {
  if (!listContainer) return;
  listContainer.replaceChildren(message("Chargement des notes…"));
  await Promise.all([loadStats(), loadNotes()]);
}

async function loadStats() {
  try {
    stats = await fetchSecondBrainStats();
  } catch (err) {
    console.warn("[Second cerveau] Compteurs indisponibles :", err);
    stats = {};
  }
  renderChips();
}

async function loadNotes() {
  try {
    const data = await fetchSecondBrainNotes({ ...notesQuery(selected), search: search || null, limit: 100 });
    notes = data.items || [];
    renderNotes();
  } catch (err) {
    notes = [];
    listContainer.replaceChildren(message(err.message || "Impossible de charger les notes.", "shopping-note--error"));
  }
}

// ---------- Puces de catégorie ----------

function renderChips() {
  if (!chipsContainer) return;
  chipsContainer.replaceChildren(...noteChips(stats, selected).map((chip) => {
    const node = button("chip", chip.text);
    node.setAttribute("role", "tab");
    node.setAttribute("aria-selected", String(chip.selected));
    node.setAttribute("aria-controls", "second-brain-list");
    node.addEventListener("click", () => selectChip(chip.key));
    return node;
  }));
  const current = chipsContainer.querySelector('[aria-selected="true"]');
  if (current && current.scrollIntoView) current.scrollIntoView({ block: "nearest", inline: "nearest" });
}

function selectChip(key) {
  if (key === selected) return;
  selected = key;
  renderChips();
  listContainer.replaceChildren(message("Chargement des notes…"));
  loadNotes();
}

// ---------- Cartes ----------

function dotsIcon() {
  const svg = document.createElementNS(SVG_NS, "svg");
  for (const [name, value] of Object.entries({
    viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "2.2",
    "stroke-linecap": "round", "aria-hidden": "true",
  })) svg.setAttribute(name, value);
  for (const cx of ["5", "12", "19"]) {
    const dot = document.createElementNS(SVG_NS, "circle");
    dot.setAttribute("cx", cx);
    dot.setAttribute("cy", "12");
    dot.setAttribute("r", "1");
    svg.append(dot);
  }
  return svg;
}

function closeMenus(except = null) {
  if (!listContainer) return;
  listContainer.querySelectorAll(".menu-pop:not([hidden])").forEach((menu) => {
    if (menu === except) return;
    menu.hidden = true;
    const opener = menu.previousElementSibling;
    if (opener) opener.setAttribute("aria-expanded", "false");
  });
}

function cardMenu(note) {
  const anchor = el("div", "menu-anchor");
  const menuId = `note-menu-${note.id}`;
  const opener = button("icon-btn note-card__more", null, "Plus d'options");
  opener.setAttribute("aria-haspopup", "menu");
  opener.setAttribute("aria-expanded", "false");
  opener.setAttribute("aria-controls", menuId);
  opener.append(dotsIcon());
  const menu = el("div", "menu-pop");
  menu.id = menuId;
  menu.setAttribute("role", "menu");
  menu.hidden = true;
  const remove = button("menu-pop__item menu-pop__item--danger", "Supprimer");
  remove.setAttribute("role", "menuitem");
  remove.addEventListener("click", () => {
    closeMenus();
    deleteNote(note);
  });
  menu.append(remove);
  opener.addEventListener("click", () => {
    const open = menu.hidden;
    closeMenus(menu);
    menu.hidden = !open;
    opener.setAttribute("aria-expanded", String(open));
    if (open) remove.focus();
  });
  menu.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    event.stopPropagation(); // Échap ferme le menu, pas la feuille
    closeMenus();
    opener.focus();
  });
  anchor.append(opener, menu);
  return anchor;
}

const ACTIONS = {
  done: { text: "Fait", className: "btn note-card__done", run: (note, card) => markDone(note, card) },
  task: { text: "En faire une tâche", className: "btn", run: (note, card) => makeTask(note, card) },
  reopen: { text: "Rouvrir", className: "btn note-card__done", run: (note, card) => reopenNote(note, card) },
};

function noteArticle(note) {
  const view = noteCard(note, new Date());
  const card = el("article", `note-card${view.done ? " note-card--done" : ""}`);
  const head = el("div", "note-card__head");
  const meta = el("div", "note-card__meta");
  meta.append(el("span", "note-card__date", view.date), cardMenu(note));
  head.append(el("span", `note-card__label note-card__label--${view.tone}`, view.label), meta);
  const actions = el("div", "note-card__actions");
  actions.append(...view.actions.map((key) => {
    const action = ACTIONS[key];
    const node = button(action.className, action.text);
    node.addEventListener("click", () => action.run(note, card));
    return node;
  }));
  card.append(head, el("p", "note-card__text", view.text), actions);
  return card;
}

function renderNotes() {
  if (!notes.length) {
    listContainer.replaceChildren(message(emptyText(selected, search)));
    return;
  }
  listContainer.replaceChildren(...notes.map(noteArticle));
}

// Écriture en cours : boutons de la carte désactivés (pas de double envoi).
function setBusy(card, busy) {
  card.querySelectorAll("button").forEach((node) => { node.disabled = busy; });
}

function dropNote(note) {
  notes = notes.filter((n) => n.id !== note.id);
  renderNotes();
  loadStats();
}

async function refresh() {
  await Promise.all([loadStats(), loadNotes()]);
}

// ---------- Actions ----------

async function markDone(note, card) {
  setBusy(card, true);
  try {
    await patchSecondBrainNote(note.id, { status: "done" });
  } catch (err) {
    setBusy(card, false);
    showToastError(err.message, "Note non marquée faite");
    return;
  }
  dropNote(note);
  showToast("Retrouve-la dans « Faites ».", "success", {
    title: "Note faite", duration: 6000, action: { label: "Annuler", onClick: () => undoDone(note) },
  });
}

async function undoDone(note) {
  try {
    await patchSecondBrainNote(note.id, { status: "active" });
  } catch (err) {
    showToastError(err.message, "Note non rouverte");
    return;
  }
  await refresh();
}

async function reopenNote(note, card) {
  setBusy(card, true);
  try {
    await patchSecondBrainNote(note.id, { status: "active" });
  } catch (err) {
    setBusy(card, false);
    showToastError(err.message, "Note non rouverte");
    return;
  }
  dropNote(note);
  showToastSuccess("La note est de nouveau active.", "Note rouverte");
}

// Tâche Google (titre = texte, sans date) puis note faite ; si la note ne peut pas passer « faite », la tâche est retirée.
async function makeTask(note, card) {
  setBusy(card, true);
  let task;
  try {
    task = await createTask(taskTitle(note));
  } catch (err) {
    setBusy(card, false);
    showToastError(err.message, "Tâche non créée");
    return;
  }
  try {
    await patchSecondBrainNote(note.id, { status: "done" });
  } catch (err) {
    setBusy(card, false);
    await deleteTask(task.id).catch((rollbackErr) => {
      showToastError(`La tâche « ${task.titre} » a été créée mais n'a pas pu être retirée : ${rollbackErr.message}`, "Tâche en double");
    });
    showToastError(err.message, "Note non marquée faite");
    return;
  }
  dropNote(note);
  showToast(`« ${task.titre} » est dans tes tâches.`, "success", {
    title: "Tâche créée", duration: 6000, action: { label: "Annuler", onClick: () => undoTask(note, task) },
  });
}

async function undoTask(note, task) {
  try {
    await deleteTask(task.id);
  } catch (err) {
    showToastError(err.message, "Tâche non supprimée");
    return;
  }
  try {
    await patchSecondBrainNote(note.id, { status: "active" });
  } catch (err) {
    showToastError(err.message, "Note non rouverte");
  }
  await refresh();
}

async function deleteNote(note) {
  try {
    await deleteSecondBrainNote(note.id);
  } catch (err) {
    showToastError(err.message, "Note non supprimée");
    return;
  }
  dropNote(note);
  showToast("La note a été supprimée.", "success", {
    title: "Note supprimée", duration: 6000, action: { label: "Annuler", onClick: () => restoreNote(note) },
  });
}

// Note recréée (nouvel identifiant) avec sa catégorie, ses mots-clés, sa date et son statut d'origine.
async function restoreNote(note) {
  try {
    const created = await createSecondBrainNote(restorePayload(note));
    if (note.status === "done") await patchSecondBrainNote(created.id, { status: "done" });
  } catch (err) {
    showToastError(err.message, "Note non rétablie");
    return;
  }
  await refresh();
}

// ---------- Recherche (loupe) ----------

function setSearchOpen(open) {
  if (!searchBox || !searchButton) return;
  searchBox.hidden = !open;
  searchButton.setAttribute("aria-expanded", String(open));
  if (open) {
    searchInput.focus();
    return;
  }
  if (searchInput) searchInput.value = "";
  search = "";
}

function initSearch() {
  if (!searchButton || !searchInput) return;
  searchButton.addEventListener("click", () => {
    const open = searchBox.hidden;
    const hadSearch = !!search;
    setSearchOpen(open);
    if (!open && hadSearch) loadNotes();
  });
  let timer = null;
  searchInput.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      search = searchInput.value.trim();
      loadNotes();
    }, 300);
  });
  searchInput.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    event.stopPropagation(); // Échap ferme la recherche, pas la feuille
    const hadSearch = !!search;
    setSearchOpen(false);
    searchButton.focus();
    if (hadSearch) loadNotes();
  });
}

// ---------- Capture collée (Ctrl+V sur ordinateur) ----------

async function pasteImage(file) {
  try {
    const res = await uploadSecondBrainImage(file, { caption: "Capture collée depuis le presse-papier" });
    showToastSuccess(res.analysis.title, "Capture enregistrée");
  } catch (err) {
    showToastError(err.message, "Capture non analysée");
    return;
  }
  await refresh();
}

export function initSecondBrainView() {
  initSearch();
  document.addEventListener("click", (event) => {
    if (listContainer && !event.target.closest(".note-card .menu-anchor")) closeMenus();
  });
  window.addEventListener("paste", (event) => {
    if (!isOpen()) return;
    const items = event.clipboardData ? Array.from(event.clipboardData.items) : [];
    const image = items.find((item) => item.type.startsWith("image/"));
    const file = image && image.getAsFile();
    if (!file) return;
    event.preventDefault();
    pasteImage(file);
  });
  // Photo de la barre de saisie rangée dans le Second cerveau (chat_view.js) : la feuille ouverte se met à jour.
  window.addEventListener("second-brain-updated", () => {
    if (isOpen()) refresh();
  });
}
