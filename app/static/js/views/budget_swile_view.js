// Feuille « Import Swile » (Phase 10, étape 8) : captures de l'appli Swile → relecture → écriture dans le classeur.
// Bouton appareil photo de l'en-tête Budget ; lignes à cocher (doublons décochés), catégorie modifiable par le champ
// à suggestions, solde « ancien → nouveau » ; l'import est une seule action annulable (toast puis « Dernières actions »).
import { analyzeSwileCaptures, importSwileLines, undoRecentAction } from "../api.js";
import { getActiveSessionId } from "../config.js";
import { showToastSuccess, showToastError } from "../toast.js";
import {
  swileState, swileLineTexts, swileBalanceText, swileImportLabel, swileChoices, swileToPayload,
} from "../budget_swile_model.js";
import { bindCombo } from "./budget_combo.js";
import { el } from "./sport/dom.js";

export const BUDGET_SWILE_SHEET_ID = "view-budget-swile";

let manager = null;
let getOverview = () => ({});
let onChanged = () => {};
let state = null;
let saving = false;

const $ = (id) => document.getElementById(id);
const scroller = () => document.querySelector(`#${BUDGET_SWILE_SHEET_ID} .sheet__body`);

const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

function setStatus(text) {
  const status = $("budget-swile-status");
  status.textContent = text;
  status.hidden = !text;
}

function showErrors(errors) {
  const box = $("budget-swile-errors");
  box.textContent = errors.join(" ");
  box.hidden = errors.length === 0;
}

function refreshButton() {
  const submit = $("btn-budget-swile-import");
  submit.textContent = state ? swileImportLabel(state) : "Rien à importer";
  submit.disabled = !state || submit.textContent === "Rien à importer";
}

function lineRow(line, index) {
  const texts = swileLineTexts(line);
  const row = el("div", "budget-swile__line");
  const check = el("input");
  check.type = "checkbox";
  check.checked = line.checked;
  check.setAttribute("aria-label", `Importer ${texts.title} du ${texts.meta}`);
  check.addEventListener("change", () => {
    line.checked = check.checked;
    refreshButton();
  });
  const text = el("div", "budget-swile__text");
  text.append(el("strong", null, texts.title), el("span", "budget-swile__meta", texts.meta));
  if (texts.note) text.append(el("span", `budget-swile__note${line.doublon ? " budget-swile__note--dup" : ""}`, texts.note));
  const combo = el("div", "budget-combo budget-swile__combo");
  const category = el("input", "input budget-swile__category");
  category.type = "text";
  category.id = `budget-swile-${index}-categorie`;
  category.placeholder = line.type === "credit" ? "Type de revenu" : "Catégorie";
  category.autocomplete = "off";
  category.setAttribute("autocapitalize", "off");
  category.setAttribute("aria-label", `Catégorie de ${texts.title} (${texts.meta})`);
  category.value = line.categorie;
  const list = el("ul", "budget-combo__list");
  list.id = `budget-swile-${index}-suggestions`;
  list.hidden = true;
  const sync = () => { line.categorie = category.value; };
  category.addEventListener("input", sync);
  category.addEventListener("change", sync);
  bindCombo({
    input: category, list, anchor: row, form: $("budget-swile-form"), scroller: scroller(),
    getChoices: () => swileChoices(getOverview(), line), onPick: () => category.blur(),
  });
  combo.append(category, list);
  row.append(check, text, combo);
  return row;
}

function render() {
  const warnings = $("budget-swile-warnings");
  warnings.replaceChildren(...state.warnings.map((w) => el("li", null, w)));
  warnings.hidden = state.warnings.length === 0;
  const balanceRow = $("budget-swile-balance-row");
  balanceRow.hidden = !state.balance;
  if (state.balance) {
    $("budget-swile-balance").textContent = swileBalanceText(state.balance);
    $("budget-swile-balance-check").checked = state.balance.checked;
  }
  $("budget-swile-lines").replaceChildren(...state.lines.map(lineRow));
  refreshButton();
}

function reset(status) {
  state = null;
  setStatus(status);
  $("budget-swile-warnings").hidden = true;
  $("budget-swile-balance-row").hidden = true;
  $("budget-swile-lines").replaceChildren();
  showErrors([]);
  refreshButton();
}

async function analyze(files, trigger) {
  reset(`Lecture de ${files.length > 1 ? `${files.length} captures` : "la capture"}…`);
  manager.openSheet(BUDGET_SWILE_SHEET_ID, trigger);
  try {
    state = swileState(await analyzeSwileCaptures(files, todayIso()));
    setStatus("");
    render();
  } catch (err) {
    setStatus("");
    showErrors([err.message]);
  }
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
  if (saving || !state) return;
  const { errors, payload } = swileToPayload(state, getActiveSessionId(), getOverview());
  showErrors(errors);
  if (errors.length) return;
  saving = true;
  $("btn-budget-swile-import").disabled = true;
  try {
    const res = await importSwileLines(payload);
    showToastSuccess(res.message, "Budget", { action: { label: "Annuler", onClick: () => undo(res.action_id) } });
    manager.closeTop();
    onChanged();
  } catch (err) {
    showErrors([err.message]);
  } finally {
    saving = false;
    refreshButton();
  }
}

// `overview()` : dernière vue d'ensemble chargée (catégories) ; `changed` : rechargement de l'écran Budget.
export function initBudgetSwile(sheetManager, { overview, changed }) {
  manager = sheetManager;
  getOverview = () => overview() || {};
  onChanged = changed;
  const button = $("btn-budget-swile");
  const input = $("budget-swile-file");
  if (!button || !input) return;
  button.addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    const files = [...input.files];
    input.value = ""; // la même capture peut être rechoisie
    if (files.length) analyze(files, button);
  });
  $("budget-swile-balance-check").addEventListener("change", (e) => {
    if (state && state.balance) state.balance.checked = e.target.checked;
    refreshButton();
  });
  $("budget-swile-form").addEventListener("submit", save);
}
