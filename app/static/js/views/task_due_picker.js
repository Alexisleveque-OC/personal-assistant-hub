// Barre de saisie de la feuille Tâches (maquette E-Taches) : bouton calendrier → date + heure facultative.
// Le choix (state.composerDue) est joint en clair au message envoyé à Otis (withDue, chat_view.js), puis effacé.
import { state } from "../config.js";
import { dueChipLabel } from "../tasks_model.js";

const dueButton = document.getElementById("btn-composer-due");
const dueLabel = document.getElementById("composer-due-label");
const pop = document.getElementById("composer-due-pop");
const dateInput = document.getElementById("composer-due-date");
const timeInput = document.getElementById("composer-due-time");
const okButton = document.getElementById("btn-composer-due-ok");
const clearButton = document.getElementById("btn-composer-due-clear");
const photoButton = document.getElementById("btn-chat-upload-image");

function localIso(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function renderLabel() {
  if (!dueLabel || !dueButton) return;
  const due = state.composerDue;
  dueLabel.hidden = !due;
  dueLabel.textContent = due ? dueChipLabel(due) : "";
  dueButton.classList.toggle("icon-btn--accent", Boolean(due));
}

function setOpen(open) {
  if (!pop || !dueButton) return;
  pop.hidden = !open;
  dueButton.setAttribute("aria-expanded", String(open));
  if (!open) return;
  const due = state.composerDue;
  dateInput.value = due ? due.date : localIso(new Date());
  timeInput.value = due ? due.time : "";
  dateInput.focus();
}

export function clearComposerDue() {
  state.composerDue = null;
  renderLabel();
}

// Calendrier visible dans la feuille Tâches seulement (la photo y est masquée, comme sur la maquette).
export function setDuePickerVisible(visible) {
  if (!dueButton) return;
  dueButton.hidden = !visible;
  if (photoButton) photoButton.hidden = visible;
  if (!visible) {
    setOpen(false);
    clearComposerDue();
  }
}

export function initDuePicker() {
  if (!dueButton || !pop) return;
  dueButton.addEventListener("click", () => setOpen(pop.hidden));
  if (dueLabel) dueLabel.addEventListener("click", () => setOpen(true));
  okButton.addEventListener("click", () => {
    if (!dateInput.value) {
      dateInput.focus(); // une heure seule n'a pas de sens : la date est requise
      return;
    }
    state.composerDue = { date: dateInput.value, time: timeInput.value || "" };
    renderLabel();
    setOpen(false);
    dueButton.focus();
  });
  clearButton.addEventListener("click", () => {
    clearComposerDue();
    setOpen(false);
    dueButton.focus();
  });
  pop.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    event.stopPropagation(); // Échap ferme la fenêtre de date, pas la feuille
    setOpen(false);
    dueButton.focus();
  });
  document.addEventListener("click", (event) => {
    if (pop.hidden || pop.contains(event.target) || dueButton.contains(event.target)) return;
    if (dueLabel && dueLabel.contains(event.target)) return;
    setOpen(false);
  });
}
