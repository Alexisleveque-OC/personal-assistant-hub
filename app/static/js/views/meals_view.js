// Feuille Repas (refonte UX, maquette E-Repas ; décisions du 17/11) : lecture directe de GET /api/v1/meals/week.
// Bande des 7 jours (samedi → vendredi) ; sous la bande, le jour choisi + le lendemain (Midi / Soir, chevron = ingrédients).
// « Ajouter » pré-remplit la barre ; « Demander une idée à Otis » demande des propositions sans écriture ;
// « Ingrédients de la semaine → courses » : liste à cocher, l'ajout passe par Otis (rayons inconnus, Annuler).
import { fetchShoppingData, fetchWeekMeals } from "../api.js";
import {
  dayCards, defaultDay, ideaPrompt, ingredientsMessage, slotPrefill, weekIngredients, weekStrip,
} from "../meals_model.js";
import { sendInteraction } from "./chat_view.js";
import { button, el } from "./sport/dom.js";

const daysStrip = document.getElementById("meal-days");
const mealContainer = document.getElementById("meal-container");
const ingredientsButton = document.getElementById("btn-meal-ingredients");
const ingredientsPanel = document.getElementById("meal-ingredients");
const queryInput = document.getElementById("query-input");
const SVG_NS = "http://www.w3.org/2000/svg";

let week = [];
let selected = -1;

function note(text, className = "muted") {
  return el("p", `shopping-note ${className}`, text);
}

function chevronDown() {
  const svg = document.createElementNS(SVG_NS, "svg");
  for (const [name, value] of Object.entries({
    viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "2",
    "stroke-linecap": "round", "aria-hidden": "true", class: "meal-row__chevron",
  })) svg.setAttribute(name, value);
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", "M6 9l6 6 6-6");
  svg.append(path);
  return svg;
}

export function initMealsView() {
  if (!ingredientsButton || !ingredientsPanel) return;
  ingredientsButton.addEventListener("click", () => {
    if (ingredientsPanel.hidden) openIngredients();
    else closeIngredients();
  });
}

export async function loadMeals() {
  if (!mealContainer) return;
  closeIngredients();
  mealContainer.replaceChildren(note("Chargement des repas…"));
  try {
    const data = await fetchWeekMeals();
    week = data.week_plan || [];
  } catch (err) {
    week = [];
    if (daysStrip) daysStrip.replaceChildren();
    mealContainer.replaceChildren(note(err.message || "Impossible de charger les repas.", "shopping-note--error"));
    return;
  }
  if (selected < 0 || selected >= week.length) selected = defaultDay(week);
  render();
}

function render() {
  renderStrip();
  if (!week.length) {
    mealContainer.replaceChildren(note("Aucun repas dans la feuille « Cette semaine »."));
    return;
  }
  mealContainer.replaceChildren(...dayCards(week, selected).flatMap(renderCard));
}

function renderStrip() {
  if (!daysStrip) return;
  daysStrip.replaceChildren(...weekStrip(week).map((day) => {
    const tab = button(`meal-day meal-day--${day.state}`, undefined, day.name);
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-selected", String(day.index === selected));
    tab.append(el("span", "meal-day__short", day.short), el("span", "meal-day__num", day.num));
    tab.addEventListener("click", () => {
      selected = day.index;
      render();
    });
    return tab;
  }));
}

function renderCard(card) {
  const title = el("span", "section-label", card.title);
  if (card.empty) {
    const box = el("div", "meal-empty");
    const ask = button("btn btn--light", "Demander une idée à Otis");
    ask.addEventListener("click", () => sendInteraction(ideaPrompt(week, card.index)));
    box.append(el("p", "meal-empty__text", "Rien de planifié pour l'instant."), ask);
    return [title, box];
  }
  const group = el("div", "list-group");
  group.append(...card.slots.map((slot) => renderSlot(card.index, slot)));
  return [title, group];
}

function renderSlot(dayIndex, slot) {
  const wrap = el("div", "meal-slot");
  const label = el("span", `meal-row__label${slot.dish ? " meal-row__label--accent" : ""}`, slot.label);
  if (!slot.dish) {
    const row = el("div", "meal-row");
    const add = button("btn meal-row__add", "Ajouter", `Ajouter le repas : ${slot.label.toLowerCase()}`);
    add.addEventListener("click", () => prefill(slotPrefill(week, dayIndex, slot.key)));
    row.append(label, el("span", "meal-row__dish meal-row__dish--empty", "Rien de prévu"), add);
    wrap.append(row);
    return wrap;
  }
  if (!slot.ingredients.length) {
    const row = el("div", "meal-row");
    row.append(label, el("span", "meal-row__dish", slot.dish));
    wrap.append(row);
    return wrap;
  }
  const toggle = button("meal-row meal-row--toggle");
  toggle.setAttribute("aria-expanded", "false");
  toggle.append(label, el("span", "meal-row__dish", slot.dish), chevronDown());
  const chips = el("div", "chips meal-row__ingredients");
  chips.hidden = true;
  chips.append(...slot.ingredients.map((name) => el("span", "chip", name)));
  toggle.addEventListener("click", () => {
    chips.hidden = !chips.hidden;
    toggle.setAttribute("aria-expanded", String(!chips.hidden));
  });
  wrap.append(toggle, chips);
  return wrap;
}

// La barre de saisie reçoit « Midi mardi 17 : » : on tape ou dicte le plat, Otis l'écrit (set_meal, annulable).
function prefill(text) {
  if (!queryInput) return;
  queryInput.value = text;
  queryInput.focus();
  queryInput.setSelectionRange(text.length, text.length);
}

function closeIngredients() {
  if (!ingredientsPanel || !ingredientsButton) return;
  ingredientsPanel.hidden = true;
  ingredientsPanel.replaceChildren();
  ingredientsButton.setAttribute("aria-expanded", "false");
}

async function openIngredients() {
  ingredientsPanel.hidden = false;
  ingredientsButton.setAttribute("aria-expanded", "true");
  ingredientsPanel.replaceChildren(note("Chargement de la liste de courses…"));
  let shopping;
  try {
    shopping = await fetchShoppingData();
  } catch (err) {
    ingredientsPanel.replaceChildren(note(err.message || "Liste de courses indisponible.", "shopping-note--error"));
    return;
  }
  const items = weekIngredients(week, shopping);
  if (!items.length) {
    ingredientsPanel.replaceChildren(note("Aucun ingrédient connu pour les repas d'ici vendredi."));
    return;
  }
  renderIngredients(items);
}

function renderIngredients(items) {
  const group = el("div", "list-group");
  const boxes = items.map((item) => {
    const row = el("label", "list-row");
    const box = el("input", "check");
    box.type = "checkbox";
    box.checked = !item.listed; // déjà dans la liste : décoché, mais on peut le recocher
    row.append(box, el("span", "list-row__text", item.name));
    if (item.listed) row.append(el("span", "badge badge--muted", "déjà dans la liste"));
    group.append(row);
    return { box, name: item.name };
  });
  const submit = button("btn btn--primary btn--block");
  const refresh = () => {
    const count = boxes.filter((b) => b.box.checked).length;
    submit.textContent = count ? `Ajouter aux courses (${count})` : "Ajouter aux courses";
    submit.disabled = count === 0;
  };
  boxes.forEach((b) => b.box.addEventListener("change", refresh));
  submit.addEventListener("click", () => {
    const names = boxes.filter((b) => b.box.checked).map((b) => b.name);
    if (!names.length) return;
    closeIngredients();
    sendInteraction(ingredientsMessage(names));
  });
  refresh();
  ingredientsPanel.replaceChildren(group, submit);
  ingredientsButton.scrollIntoView({ block: "start", behavior: "smooth" }); // la liste s'ouvre sous la ligne de flottaison
}
