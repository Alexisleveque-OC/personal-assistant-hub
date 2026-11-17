// Feuille Repas (refonte UX, maquette E-Repas ; décisions et retours du 17/11).
// Lecture directe de GET /api/v1/meals/week?offset=N (onglet annuel « repas AAAA », même source qu'Otis).
// En-tête collant : ‹ semaine › + bande des 7 jours (toucher un jour fait défiler jusqu'à sa carte) ;
// dessous, les 7 jours en cartes Midi / Soir (chevron = ingrédients). « Ajouter » pré-remplit la barre ;
// « Demander une idée à Otis » demande des propositions sans écriture ; « Ingrédients de la semaine → courses » :
// liste à cocher de la semaine affichée (à partir d'aujourd'hui), l'ajout passe par Otis (rayons inconnus, Annuler).
import { fetchShoppingData, fetchWeekMeals } from "../api.js";
import {
  dayCards, defaultDay, hasIngredientsButton, ideaPrompt, ingredientsMessage, slotPrefill, weekIngredients, weekNav,
  weekStrip,
} from "../meals_model.js";
import { sendInteraction } from "./chat_view.js";
import { button, el, periodNav } from "./sport/dom.js";

const navSlot = document.getElementById("meal-nav");
const daysStrip = document.getElementById("meal-days");
const mealContainer = document.getElementById("meal-container");
const ingredientsButton = document.getElementById("btn-meal-ingredients");
const ingredientsPanel = document.getElementById("meal-ingredients");
const queryInput = document.getElementById("query-input");
const SVG_NS = "http://www.w3.org/2000/svg";

let offset = 0;
let week = [];
let range = { start: "", end: "" };
let loadedOffset = null; // semaine affichée : un rechargement de la même semaine garde la position de défilement
let selected = -1;
let scrollTarget = null; // carte à amener sous l'en-tête après le prochain chargement

function todayIso() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

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

// Ouverture de la feuille : retour sur la semaine en cours, défilement jusqu'à aujourd'hui.
export function resetMealsWeek() {
  offset = 0;
  loadedOffset = null;
  selected = -1;
  scrollTarget = "today";
}

function goToWeek(newOffset) {
  offset = newOffset;
  selected = -1;
  scrollTarget = "today"; // aujourd'hui s'il est dans la semaine, sinon le premier jour
  loadMeals();
}

export async function loadMeals() {
  if (!mealContainer) return;
  closeIngredients();
  const requested = offset;
  if (loadedOffset !== requested) mealContainer.replaceChildren(note("Chargement des repas…"));
  let data;
  try {
    data = await fetchWeekMeals(requested);
  } catch (err) {
    if (requested !== offset) return; // une autre semaine a été demandée entre-temps
    week = [];
    loadedOffset = null;
    renderNav();
    if (daysStrip) daysStrip.replaceChildren();
    if (ingredientsButton) ingredientsButton.hidden = true;
    mealContainer.replaceChildren(note(err.message || "Impossible de charger les repas.", "shopping-note--error"));
    return;
  }
  if (requested !== offset) return;
  week = data.week_plan || [];
  range = { start: data.start, end: data.end };
  loadedOffset = requested;
  const today = todayIso();
  if (selected < 0 || selected >= week.length) selected = defaultDay(week, today);
  render(today);
  if (scrollTarget !== null) {
    scrollToCard(selected, "auto");
    scrollTarget = null;
  }
}

function render(today) {
  renderNav();
  renderStrip(today);
  if (ingredientsButton) ingredientsButton.hidden = !hasIngredientsButton(week, today);
  if (!week.length) {
    mealContainer.replaceChildren(note("Aucun jour à afficher pour cette semaine."));
    return;
  }
  mealContainer.replaceChildren(...dayCards(week, today).map(renderCard));
}

function renderNav() {
  if (!navSlot) return;
  const label = range.start ? weekNav(offset, range.start, range.end) : { title: "Repas", range: "" };
  const center = button("period-nav__label meal-nav__label");
  center.append(el("strong", null, label.title));
  if (label.range) center.append(el("span", null, label.range));
  if (offset === 0) center.disabled = true;
  else center.setAttribute("aria-label", `Revenir à cette semaine (${label.title}, ${label.range})`);
  center.addEventListener("click", () => goToWeek(0));
  navSlot.replaceChildren(periodNav({
    center,
    prevLabel: "Semaine précédente",
    nextLabel: "Semaine suivante",
    onPrev: () => goToWeek(offset - 1),
    onNext: () => goToWeek(offset + 1),
  }));
}

function renderStrip(today) {
  if (!daysStrip) return;
  daysStrip.replaceChildren(...weekStrip(week, today).map((day) => {
    const tab = button(`meal-day meal-day--${day.state}`, undefined, day.name);
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-selected", String(day.index === selected));
    tab.setAttribute("aria-controls", `meal-card-${day.index}`);
    tab.append(el("span", "meal-day__short", day.short), el("span", "meal-day__num", day.num));
    tab.addEventListener("click", () => {
      selected = day.index;
      daysStrip.querySelectorAll(".meal-day").forEach((b, i) => b.setAttribute("aria-selected", String(i === selected)));
      scrollToCard(selected, "smooth");
    });
    return tab;
  }));
}

function scrollToCard(index, behavior) {
  const target = document.getElementById(`meal-card-${index}`);
  if (target) target.scrollIntoView({ block: "start", behavior });
}

function renderCard(card) {
  const box = el("div", "meal-card");
  box.id = `meal-card-${card.index}`;
  box.append(el("span", "section-label", card.title));
  if (card.empty) {
    const empty = el("div", "meal-empty");
    const ask = button("btn btn--light", "Demander une idée à Otis");
    ask.addEventListener("click", () => sendInteraction(ideaPrompt(week, card.index)));
    empty.append(el("p", "meal-empty__text", "Rien de planifié pour l'instant."), ask);
    box.append(empty);
    return box;
  }
  const group = el("div", "list-group");
  group.append(...card.slots.map((slot) => renderSlot(card.index, slot)));
  box.append(group);
  return box;
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

// La barre de saisie reçoit « Midi mardi 17 novembre : » : on tape ou dicte le plat, Otis l'écrit (set_meal, annulable).
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
  const items = weekIngredients(week, shopping, todayIso());
  if (!items.length) {
    ingredientsPanel.replaceChildren(note("Aucun ingrédient connu pour les repas restants de cette semaine."));
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
