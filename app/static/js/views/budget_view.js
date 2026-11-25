// Feuille Budget (Phase 10, étape 7a) : suivi en lecture seule du classeur Budget.
// En tête : épargné du mois actif et graphique Dépenses vs Revenus par mois (toucher une colonne affiche ses montants).
// Puis les groupes de `Gestion`, repliés à l'ouverture (décision du 25/11) : par catégorie, le reste total et
// « ce mois : dépensé X / budget Y » avec sa barre. La saisie passe par la barre d'Otis (formulaires en 7b / 7c).
import { fetchBudgetOverview } from "../api.js";
import { budgetSheet } from "../budget_model.js";
import { el, button } from "./sport/dom.js";

const container = document.getElementById("budget-container");
const monthLabel = document.getElementById("budget-month");

function note(text, className = "muted") {
  return el("p", `shopping-note ${className}`, text);
}

export async function loadBudget() {
  if (!container) return;
  container.replaceChildren(note("Chargement du budget…"));
  try {
    render(budgetSheet(await fetchBudgetOverview()));
  } catch (err) {
    if (monthLabel) monthLabel.textContent = "";
    container.replaceChildren(note(err.message || "Impossible de charger le budget.", "shopping-note--error"));
  }
}

function summaryCard(sheet) {
  const card = el("div", "card budget-summary");
  const saved = el("div", "budget-saved");
  saved.append(
    el("span", "budget-saved__label", "Épargné ce mois"),
    el("strong", `budget-amount budget-amount--${sheet.saved.tone}`, sheet.saved.text),
  );
  const current = sheet.chart.find((bar) => bar.current) || sheet.chart[sheet.chart.length - 1];
  const caption = el("p", "budget-chart__caption", current ? current.label : "");
  caption.setAttribute("aria-live", "polite");
  const grid = el("div", "bars budget-bars");
  const axis = el("div", "bars__axis");
  sheet.chart.forEach((bar) => {
    const col = button("bars__col", null, bar.label);
    if (bar.current) col.setAttribute("aria-current", "true");
    const pair = el("span", "budget-bars__pair");
    for (const [kind, data] of [["exp", bar.expenses], ["inc", bar.income]]) {
      const fill = el("span", `bars__bar budget-bar--${kind}`);
      fill.style.setProperty("--h", `${data.pct}%`);
      pair.append(fill);
    }
    col.append(pair);
    col.addEventListener("click", () => { caption.textContent = bar.label; });
    grid.append(col);
    axis.append(el("span", null, bar.axis));
  });
  const legend = el("div", "budget-legend");
  legend.append(el("span", "budget-legend__exp", "Dépenses"), el("span", "budget-legend__inc", "Revenus"));
  card.append(saved, el("span", "sport-chart__title", "Dépenses vs revenus"), grid, axis, legend, caption);
  return card;
}

function categoryRow(cat) {
  const row = el("div", "budget-cat");
  const head = el("div", "budget-cat__head");
  head.append(
    el("span", "budget-cat__name", cat.name),
    el("strong", `budget-amount budget-amount--${cat.remaining.tone}`, cat.remaining.text),
  );
  const bar = el("div", `progress progress--sm${cat.over ? " progress--warn" : ""}`);
  bar.setAttribute("role", "progressbar");
  bar.setAttribute("aria-valuenow", String(cat.pct));
  bar.setAttribute("aria-valuemin", "0");
  bar.setAttribute("aria-valuemax", "100");
  bar.setAttribute("aria-label", `${cat.name}, ${cat.detail}`);
  const fill = el("span");
  fill.style.setProperty("--value", `${cat.pct}%`);
  bar.append(fill);
  row.append(head, el("span", "budget-cat__detail", cat.detail), bar);
  return row;
}

function groupBlock(group, index) {
  const block = el("section", `budget-group budget-group--${group.kind}`);
  const bodyId = `budget-group-${index}`;
  const head = button("budget-group__head");
  head.setAttribute("aria-expanded", "false");
  head.setAttribute("aria-controls", bodyId);
  head.append(
    el("span", "budget-group__name", group.name),
    el("span", `budget-amount budget-amount--${group.total.tone}`, group.total.text),
  );
  const body = el("div", "list-group budget-group__body");
  body.id = bodyId;
  body.hidden = true;
  body.append(...group.categories.map(categoryRow));
  head.addEventListener("click", () => {
    const open = head.getAttribute("aria-expanded") === "true";
    head.setAttribute("aria-expanded", open ? "false" : "true");
    body.hidden = open;
  });
  block.append(head, body);
  return block;
}

function render(sheet) {
  if (monthLabel) monthLabel.textContent = sheet.title;
  container.replaceChildren(summaryCard(sheet), ...sheet.groups.map(groupBlock));
}
