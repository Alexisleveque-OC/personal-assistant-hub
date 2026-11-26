// Feuille Budget : formulaire Dépense / Revenu (Phase 10, étape 7b), en feuille empilée.
// Mêmes écritures que la voix (« Otis : <libellé> ») ; la saisie va au journal : toast « Annuler » juste après,
// puis annulable depuis « Dernières actions » (refus si la ligne a changé depuis). Décisions du 26/11.
// Catégorie : champ texte avec suggestions (combobox ARIA) plutôt qu'une liste déroulante trop longue.
import { addBudgetEntry, undoRecentAction } from "../api.js";
import { getActiveSessionId } from "../config.js";
import { showToastSuccess, showToastError } from "../toast.js";
import { emptyBudgetForm, categoryChoices, budgetFormToPayload, matchCategories } from "../budget_form_model.js";
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
  $("budget-form-categorie").placeholder = income ? "Tape « caf », « salaire »…" : "Tape « cour », « resto »…";
  $("budget-form-categorie").value = form.categorie;
  hideSuggestions();
}

const choices = () => categoryChoices(overview || {}, form.type);

function hideSuggestions() {
  $("budget-form-suggestions").hidden = true;
  $("budget-form-categorie").setAttribute("aria-expanded", "false");
}

function pick(name) {
  $("budget-form-categorie").value = name;
  hideSuggestions();
  $("budget-form-libelle").focus();
}

// Le clavier couvre le bas de l'écran : pendant la saisie de la catégorie, le formulaire réserve de la place en bas
// (classe `is-searching`) et la feuille défile pour placer le champ juste sous son en-tête (retour du 26/11).
function liftField() {
  const body = document.querySelector(`#${BUDGET_FORM_SHEET_ID} .sheet__body`);
  const combo = $("budget-form-categorie").closest(".budget-combo");
  body.scrollTop += combo.getBoundingClientRect().top - body.getBoundingClientRect().top;
}

function showSuggestions() {
  const matches = matchCategories(choices(), $("budget-form-categorie").value);
  const options = matches.map(({ name, group }, index) => {
    const option = el("li");
    option.id = `budget-form-suggestion-${index}`;
    option.setAttribute("role", "option");
    option.append(el("span", null, name), el("small", null, group));
    option.addEventListener("click", () => pick(name));
    return option;
  });
  $("budget-form-suggestions").replaceChildren(...options);
  $("budget-form-suggestions").hidden = options.length === 0;
  $("budget-form-categorie").setAttribute("aria-expanded", String(options.length > 0));
  if (options.length) liftField();
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
  const { errors, payload } = budgetFormToPayload(form, getActiveSessionId(), choices());
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
  const input = $("budget-form-categorie");
  input.addEventListener("input", showSuggestions);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hideSuggestions();
  });
  // Le toucher d'une suggestion ne doit pas d'abord fermer la liste (perte de focus du champ).
  $("budget-form-suggestions").addEventListener("pointerdown", (e) => e.preventDefault());
  input.addEventListener("focus", () => $("budget-form").classList.add("is-searching"));
  input.addEventListener("blur", () => {
    hideSuggestions();
    $("budget-form").classList.remove("is-searching");
  });
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
