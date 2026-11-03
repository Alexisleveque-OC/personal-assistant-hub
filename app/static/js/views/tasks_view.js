// Vue Tâches (Google Tasks, liste « Mes tâches ») : lister, ajouter, cocher avec « Annuler » (Phase 8, étape 4 bis)
import { fetchTasks, createTask, setTaskCompleted } from "../api.js";
import { showToast, showToastError } from "../toast.js";

const listContainer = document.getElementById("tasks-list-container");
const addForm = document.getElementById("tasks-add-form");
const titleInput = document.getElementById("tasks-add-title");
const dueInput = document.getElementById("tasks-add-due");
const submitButton = document.getElementById("tasks-add-submit");

let openTasks = [];

export function initTasksView() {
  if (addForm) addForm.addEventListener("submit", onAddSubmit);
}

export async function loadTasks() {
  if (!listContainer) return;
  listContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted)">Chargement des tâches...</div>';
  try {
    const view = await fetchTasks();
    openTasks = view.taches || [];
    renderTasks();
  } catch (err) {
    listContainer.innerHTML = `<div style="text-align:center; padding:30px; color:var(--accent-rose)">${escapeHtml(err.message)}</div>`;
  }
}

function renderTasks() {
  if (openTasks.length === 0) {
    listContainer.innerHTML = '<div style="text-align:center; padding:40px 20px; color:var(--text-muted)"><p>Aucune tâche en cours 🎉</p></div>';
    return;
  }

  const rows = openTasks.map((task) => `
    <div class="shopping-item-row" data-task-id="${escapeHtml(task.id)}">
      <div class="custom-checkbox">
        <svg viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
      </div>
      <span class="item-label">${escapeHtml(task.titre)}</span>
      ${task.echeance ? `<span class="task-due${task.en_retard ? " overdue" : ""}">${formatDue(task)}</span>` : ""}
    </div>`).join("");

  listContainer.innerHTML = `
    <div class="rayon-card">
      <div class="rayon-card-header"><span>Mes tâches</span><span>${openTasks.length}</span></div>
      <div class="rayon-items">${rows}</div>
    </div>`;

  listContainer.querySelectorAll(".shopping-item-row").forEach((row) => {
    row.addEventListener("click", () => completeTask(row));
  });
}

async function completeTask(row) {
  if (row.classList.contains("checked")) return; // déjà en cours d'écriture : pas de double envoi
  const task = openTasks.find((t) => t.id === row.dataset.taskId);
  if (!task) return;

  row.classList.add("checked");
  try {
    await setTaskCompleted(task.id, true);
  } catch (err) {
    row.classList.remove("checked");
    showToastError(err.message, "Tâche non cochée");
    return;
  }

  openTasks = openTasks.filter((t) => t.id !== task.id);
  renderTasks();
  showToast(`« ${task.titre} » est cochée.`, "success", {
    title: "Tâche terminée",
    duration: 6000,
    action: { label: "Annuler", onClick: () => reopenTask(task) },
  });
}

async function reopenTask(task) {
  try {
    await setTaskCompleted(task.id, false);
  } catch (err) {
    showToastError(err.message, "Tâche non rouverte");
    return;
  }
  await loadTasks();
}

async function onAddSubmit(event) {
  event.preventDefault();
  const titre = titleInput.value.trim();
  if (!titre) return;

  submitButton.disabled = true;
  try {
    const created = await createTask(titre, dueInput.value || null);
    titleInput.value = "";
    dueInput.value = "";
    showToast(`« ${created.titre} » ajoutée à Mes tâches.`, "success", { title: "Tâche ajoutée" });
    await loadTasks();
  } catch (err) {
    showToastError(err.message, "Tâche non ajoutée");
  } finally {
    submitButton.disabled = false;
  }
}

function formatDue(task) {
  // « 2026-11-06 » lu en date locale (un new Date("2026-11-06") serait en UTC et pourrait reculer d'un jour)
  const [year, month, day] = task.echeance.split("-").map(Number);
  const label = new Date(year, month - 1, day).toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short" });
  return task.en_retard ? `En retard · ${label}` : label;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = String(text ?? "");
  return div.innerHTML.replace(/"/g, "&quot;"); // aussi utilisé dans un attribut (data-task-id)
}
