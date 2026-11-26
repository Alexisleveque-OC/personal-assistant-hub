// Feuille Budget : formulaire Dépense / Revenu (Phase 10, étape 7b), en feuille empilée.
// Mêmes écritures que la voix (« Otis : <libellé> ») ; la saisie va au journal : toast « Annuler » juste après,
// puis annulable depuis « Dernières actions » (refus si la ligne a changé depuis). Décisions du 26/11.
import { addBudgetEntry, undoRecentAction } from "../api.js";
import { getActiveSessionId } from "../config.js";
import { showToastSuccess, showToastError } from "../toast.js";
import { emptyBudgetForm, categoryChoices, budgetFormToPayload } from "../budget_form_model.js";
import { el } from "./sport/dom.js";

export const BUDGET_FORM_SHEET_ID = "view-budget-form";

let manager = null;
let overview = null; // dernière vue d'ensemble chargée : source des catégories
let form = null;
let saving = false;
let onChanged = () => {};

const $ = (id) => document.getElementById(id);

const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

function renderType() {
  $("budget-form-type").querySelectorAll("button[data-type]").forEach((b) => {
    b.setAttribute("aria-pressed", String(b.dataset.type === form.type));
  });
  const income = form.type === "revenu";
  $("budget-form-categorie-label").textContent = income ? "Type de revenu" : "Catégorie";
  $("budget-form-expense-options").hidden = income;
  const placeholder = el("option", null, income ? "Choisir un type…" : "Choisir une catégorie…");
  placeholder.value = "";
  const groups = categoryChoices(overview || {}, form.type).map(({ group, names }) => {
    const optgroup = el("optgroup");
    optgroup.label = group;
    optgroup.append(...names.map((name) => {
      const option = el("option", null, name);
      option.value = name;
      return option;
    }));
    return optgroup;
  });
  $("budget-form-categorie").replaceChildren(placeholder, ...groups);
  $("budget-form-categorie").value = form.categorie;
}

function render() {
  renderType();
  $("budget-form-montant").value = form.montant;
  $("budget-form-libelle").value = form.libelle;
  $("budget-form-date").value = form.date;
  $("budget-form-swile").checked = form.swile;
  $("budget-form-remboursement").checked = form.remboursement;
  showErrors([]);
}

function readFields() {
  form.montant = $("budget-form-montant").value;
  form.categorie = $("budget-form-categorie").value;
  form.libelle = $("budget-form-libelle").value;
  form.date = $("budget-form-date").value;
  form.swile = $("budget-form-swile").checked;
  form.remboursement = $("budget-form-remboursement").checked;
}

function showErrors(errors) {
  const box = $("budget-form-errors");
  box.textContent = errors.join(" ");
  box.hidden = errors.length === 0;
}

export function openBudgetForm(trigger) {
  form = emptyBudgetForm(todayIso());
  render();
  manager.openSheet(BUDGET_FORM_SHEET_ID, trigger);
  $("budget-form-montant").focus();
}

async function undo(actionId) {
  try {
    const res = await undoRecentAction(actionId, getActiveSessionId());
    showToastSuccess(res.spoken_response, "Budget");
  } catch (err) {
    showToastError(err.message, "Budget");
  }
  onChanged();
}

async function save(e) {
  e.preventDefault();
  if (saving) return;
  readFields();
  const { errors, payload } = budgetFormToPayload(form, getActiveSessionId());
  showErrors(errors);
  if (errors.length) return;
  saving = true;
  document.querySelectorAll(`#${BUDGET_FORM_SHEET_ID} [type="submit"]`).forEach((b) => { b.disabled = true; });
  try {
    const res = await addBudgetEntry(payload);
    showToastSuccess(res.message, "Budget", { action: { label: "Annuler", onClick: () => undo(res.action_id) } });
    manager.closeTop();
    onChanged();
  } catch (err) {
    showErrors([err.message]);
  } finally {
    saving = false;
    document.querySelectorAll(`#${BUDGET_FORM_SHEET_ID} [type="submit"]`).forEach((b) => { b.disabled = false; });
  }
}

// `changed` : rechargement de l'écran Budget après une saisie ou son annulation.
export function initBudgetForm(sheetManager, { changed }) {
  manager = sheetManager;
  onChanged = changed;
  $("budget-form").addEventListener("submit", save);
  $("budget-form-type").addEventListener("click", (e) => {
    const choice = e.target.closest("button[data-type]");
    if (!choice || choice.dataset.type === form.type) return;
    readFields();
    form.type = choice.dataset.type;
    form.categorie = ""; // les listes Dépense et Revenu n'ont aucune catégorie en commun
    renderType();
  });
}

export function setBudgetFormOverview(value) {
  overview = value;
}
