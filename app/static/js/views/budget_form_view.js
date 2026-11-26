// Feuille Budget : formulaires en onglets (Phase 10) — Dépense / Revenu (7b), Échéancier et Dépense multiple (7c),
// en feuille empilée. Mêmes écritures que la voix ; chaque saisie va au journal : toast « Annuler » juste après, puis
// annulable depuis « Dernières actions » (refus si la ligne a changé depuis). Décisions du 26/11.
// Catégories : champs texte avec suggestions (budget_combo.js) plutôt qu'une liste déroulante trop longue.
import { addBudgetEntry, addBudgetInstallment, addBudgetSplitExpense, undoRecentAction } from "../api.js";
import { getActiveSessionId } from "../config.js";
import { showToastSuccess, showToastError } from "../toast.js";
import { formatEuros } from "../budget_model.js";
import {
  emptyBudgetForm, categoryChoices, budgetFormToPayload, splitRemainder, fillRemainder, addPart, removePart,
} from "../budget_form_model.js";
import { bindCombo } from "./budget_combo.js";
import { el, button } from "./sport/dom.js";

export const BUDGET_FORM_SHEET_ID = "view-budget-form";

const SEND = { depense: addBudgetEntry, revenu: addBudgetEntry, echeancier: addBudgetInstallment, multiple: addBudgetSplitExpense };
const TEXT_FIELDS = {
  montant: "budget-form-montant", categorie: "budget-form-categorie", libelle: "budget-form-libelle",
  date: "budget-form-date", nom: "budget-form-nom", motCle: "budget-form-mot-cle",
  nbEcheances: "budget-form-nb-echeances", moisDebut: "budget-form-mois-debut", commentaire: "budget-form-commentaire",
};
const LABELS = {
  depense: { montant: "Montant (€)", date: "Date", categorie: "Catégorie", hint: "Tape « cour », « resto »…" },
  revenu: { montant: "Montant (€)", date: "Date", categorie: "Type de revenu", hint: "Tape « caf », « salaire »…" },
  echeancier: { montant: "Montant total (€)", date: "Date", categorie: "Catégorie", hint: "Tape « cour », « loisir »…" },
  multiple: { montant: "Montant total débité (€)", date: "Date prévue du débit", categorie: "Catégorie", hint: "" },
};

let manager = null;
let overview = null; // dernière vue d'ensemble chargée : source des catégories
let form = null;
let saving = false;
let onChanged = () => {};

const $ = (id) => document.getElementById(id);
const scroller = () => document.querySelector(`#${BUDGET_FORM_SHEET_ID} .sheet__body`);
const choices = () => categoryChoices(overview || {}, form.type);

const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

function renderType() {
  $("budget-form-type").querySelectorAll("button[data-type]").forEach((b) => {
    b.setAttribute("aria-pressed", String(b.dataset.type === form.type));
  });
  $("budget-form").querySelectorAll("[data-types]").forEach((node) => {
    node.hidden = !node.dataset.types.split(" ").includes(form.type);
  });
  const labels = LABELS[form.type];
  $("budget-form-montant-label").textContent = labels.montant;
  $("budget-form-date-label").textContent = labels.date;
  $("budget-form-categorie-label").textContent = labels.categorie;
  $("budget-form-categorie").placeholder = labels.hint;
  $("budget-form-categorie").value = form.categorie;
  renderParts();
}

// ---------- Dépense multiple : parts et reste à répartir ----------

function renderRemainder() {
  const remainder = splitRemainder(form);
  const box = $("budget-form-remainder");
  box.textContent = remainder >= 0 ? `Reste à répartir : ${formatEuros(remainder)}` : `En trop : ${formatEuros(-remainder)}`;
  box.classList.toggle("budget-parts__remainder--off", remainder < 0);
}

function partRow(part, index) {
  const row = el("div", "budget-part");
  const category = el("input", "input");
  category.type = "text";
  category.id = `budget-part-${index}-categorie`;
  category.placeholder = "Catégorie";
  category.autocomplete = "off";
  category.setAttribute("autocapitalize", "off");
  category.setAttribute("aria-label", `Catégorie de la part ${index + 1}`);
  category.value = part.categorie;
  const amount = el("input", "input");
  amount.type = "text";
  amount.inputMode = "decimal";
  amount.id = `budget-part-${index}-montant`;
  amount.placeholder = "€";
  amount.autocomplete = "off";
  amount.setAttribute("aria-label", `Montant de la part ${index + 1}`);
  amount.value = part.montant;
  const list = el("ul", "budget-combo__list");
  list.id = `budget-part-${index}-suggestions`;
  list.hidden = true;
  const rest = button("btn budget-part__rest", "Reste", `Mettre le reste dans la part ${index + 1}`);
  const remove = button("icon-btn", "×", `Retirer la part ${index + 1}`);
  remove.disabled = form.parts.length <= 1;

  category.addEventListener("input", () => { form.parts[index].categorie = category.value; });
  category.addEventListener("change", () => { form.parts[index].categorie = category.value; });
  amount.addEventListener("input", () => {
    form.parts[index].montant = amount.value;
    renderRemainder();
  });
  rest.addEventListener("click", () => {
    readFields();
    form = fillRemainder(form, index);
    renderParts();
  });
  remove.addEventListener("click", () => {
    readFields();
    form = removePart(form, index);
    renderParts();
  });
  bindCombo({
    input: category, list, anchor: row, form: $("budget-form"), scroller: scroller(), getChoices: choices,
    onPick: () => amount.focus(),
  });
  const actions = el("div", "budget-part__actions");
  actions.append(rest, remove);
  row.append(category, amount, actions, list);
  return row;
}

function renderParts() {
  $("budget-form-parts").replaceChildren(...form.parts.map(partRow));
  renderRemainder();
}

// ---------- Lecture, erreurs, envoi ----------

function render() {
  Object.entries(TEXT_FIELDS).forEach(([key, id]) => { $(id).value = form[key]; });
  $("budget-form-swile").checked = form.swile;
  $("budget-form-remboursement").checked = form.remboursement;
  renderType();
  showErrors([]);
}

function readFields() {
  Object.entries(TEXT_FIELDS).forEach(([key, id]) => { form[key] = $(id).value; });
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
  const { errors, payload } = budgetFormToPayload(form, getActiveSessionId(), choices());
  showErrors(errors);
  if (errors.length) return;
  saving = true;
  document.querySelectorAll(`#${BUDGET_FORM_SHEET_ID} [type="submit"]`).forEach((b) => { b.disabled = true; });
  try {
    const res = await SEND[form.type](payload);
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
  bindCombo({
    input: $("budget-form-categorie"), list: $("budget-form-suggestions"),
    anchor: $("budget-form-categorie").closest(".budget-combo"), form: $("budget-form"), scroller: scroller(),
    getChoices: choices, onPick: () => (form.type === "echeancier" ? $("budget-form-mois-debut") : $("budget-form-libelle")).focus(),
  });
  $("budget-form-montant").addEventListener("input", () => {
    form.montant = $("budget-form-montant").value;
    renderRemainder();
  });
  $("btn-budget-add-part").addEventListener("click", () => {
    readFields();
    form = addPart(form);
    renderParts();
    $(`budget-part-${form.parts.length - 1}-categorie`).focus();
  });
  $("budget-form-type").addEventListener("click", (e) => {
    const choice = e.target.closest("button[data-type]");
    if (!choice || choice.dataset.type === form.type) return;
    readFields();
    const wasIncome = form.type === "revenu";
    form.type = choice.dataset.type;
    if (wasIncome || form.type === "revenu") form.categorie = ""; // aucune catégorie commune avec les revenus
    renderType();
  });
}

export function setBudgetFormOverview(value) {
  overview = value;
}
