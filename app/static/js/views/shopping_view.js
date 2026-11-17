// Feuille Courses (refonte UX, maquette E-Courses) : Cette semaine / En attente, groupes par rayon, cases à cocher.
// Lecture directe (GET /api/v1/meals/shopping, sans question à Otis) ; les coches restent sur le téléphone
// jusqu'à « J'ai fini mes courses », qui les synchronise dans le classeur.
import { state, getStoredCheckedItems, setStoredCheckedItems, clearStoredCheckedItems } from "../config.js";
import { speak } from "../tts.js";
import { fetchShoppingData, postInteract, resetShoppingList, postShoppingComplete } from "../api.js";
import { showToast } from "../toast.js";
import { shoppingLists, groupByRayon, remainingCount, remainingNames, toggleStoredCheck, completionMessage } from "../shopping_model.js";
import { el, button } from "./sport/dom.js";

const WEEK = "cette-semaine";
const WAITING = "liste-attente";

const listContainer = document.getElementById("shopping-list-container");
const banner = document.getElementById("shopping-completion-banner");
const tabs = { [WEEK]: document.getElementById("tab-cette-semaine"), [WAITING]: document.getElementById("tab-liste-attente") };
const badges = { [WEEK]: document.getElementById("badge-cette-semaine"), [WAITING]: document.getElementById("badge-liste-attente") };
const moreButton = document.getElementById("btn-shopping-more");
const menu = document.getElementById("shopping-menu");

function currentLists() {
  return shoppingLists(state.cachedShoppingData, getStoredCheckedItems());
}

function updateBadges() {
  const lists = currentLists();
  if (badges[WEEK]) badges[WEEK].textContent = String(remainingCount(lists.week));
  if (badges[WAITING]) badges[WAITING].textContent = String(remainingCount(lists.waiting));
}

function note(text, className = "muted") {
  return el("p", `shopping-note ${className}`, text);
}

export async function fetchShoppingList() {
  if (!listContainer) return;
  listContainer.replaceChildren(note("Chargement des courses…"));
  try {
    const data = await fetchShoppingData();
    state.cachedShoppingData.current_week_items = data.current_week_items || [];
    state.cachedShoppingData.waiting_list = data.waiting_list || [];
    state.cachedShoppingData.rayons_order = data.rayons_order || null;
    renderShoppingItems();
  } catch (err) {
    listContainer.replaceChildren(note(err.message || "Impossible de charger les courses.", "shopping-note--error"));
  }
}

// Coche d'un article : gardée sur le téléphone (Cette semaine) ou en mémoire (En attente) jusqu'à « J'ai fini ».
function onToggle(isWaiting, name, checked) {
  if (isWaiting) {
    const target = state.cachedShoppingData.waiting_list.find((it) => it.item === name);
    if (target) target.is_bought = checked;
  } else {
    setStoredCheckedItems(toggleStoredCheck(getStoredCheckedItems(), name, checked));
    const target = state.cachedShoppingData.current_week_items.find((it) => it.name === name);
    if (target) target.checked = checked;
  }
  updateBadges();
}

function itemRow(item, isWaiting) {
  const row = el("label", "list-row");
  const box = el("input", "check");
  box.type = "checkbox";
  box.checked = item.checked;
  box.addEventListener("change", () => onToggle(isWaiting, item.name, box.checked));
  row.append(box, el("span", "list-row__text", item.label));
  if (item.qty) row.append(el("span", "list-row__qty", item.qty));
  return row;
}

function rayonGroup(group, isWaiting) {
  const card = el("div", "list-group");
  const head = el("div", "list-group__head");
  head.append(el("span", null, group.rayon), el("span", null, String(group.count)));
  card.append(head, ...group.items.map((item) => itemRow(item, isWaiting)));
  return card;
}

export function renderShoppingItems() {
  if (!listContainer) return;
  const isWaiting = state.currentShoppingSubview === WAITING;
  const lists = currentLists();
  const items = isWaiting ? lists.waiting : lists.week;
  updateBadges();

  if (!items.length) {
    listContainer.replaceChildren(note(`Aucun article dans ${isWaiting ? "la liste d'attente" : "la liste de cette semaine"}.`));
    return;
  }
  const finish = button("btn btn--primary btn--block", "🏁 J'ai fini mes courses");
  finish.addEventListener("click", checkShoppingCompletion);
  listContainer.replaceChildren(
    ...groupByRayon(items, state.cachedShoppingData.rayons_order).map((group) => rayonGroup(group, isWaiting)),
    finish,
  );
}

function showBanner(message) {
  if (!banner) return;
  const box = el("div", `callout ${message.tone === "success" ? "callout--accent" : "callout--warn"} shopping-banner`);
  box.setAttribute("role", "status");
  const body = el("div");
  body.append(el("strong", "callout__title", message.title));
  if (message.text) body.append(el("p", "callout__text", message.text));
  if (message.items.length) {
    const left = el("div", "shopping-banner__items");
    left.append(...message.items.map((name) => el("span", "badge", name)));
    body.append(left);
  }
  if (message.synced) body.append(el("p", "callout__text", "✅ Synchronisé dans votre Google Sheet (Cette semaine & Liste d'attente)"));
  box.append(body);
  banner.replaceChildren(box);
  banner.hidden = false;
  banner.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

export async function checkShoppingCompletion() {
  const lists = currentLists();
  const checkedWeek = lists.week.filter((it) => it.checked).map((it) => it.name);
  const checkedWaiting = lists.waiting.filter((it) => it.checked).map((it) => it.name);

  let synced = false;
  if (checkedWeek.length || checkedWaiting.length) {
    try {
      await postShoppingComplete({ current_week_items: checkedWeek, waiting_items: checkedWaiting });
      synced = true;
      clearStoredCheckedItems();
    } catch (err) {
      console.warn("Échec de synchronisation Google Sheets:", err);
      showToast(err.message, "error", { title: "Courses non synchronisées" });
    }
  }

  const remaining = remainingNames(state.currentShoppingSubview === WAITING ? lists.waiting : lists.week);
  const message = completionMessage(remaining, synced);
  showBanner(message);
  speak(message.speech);
}

function selectTab(subview) {
  state.currentShoppingSubview = subview;
  Object.entries(tabs).forEach(([key, tab]) => tab && tab.setAttribute("aria-selected", String(key === subview)));
  if (listContainer && tabs[subview]) listContainer.setAttribute("aria-labelledby", tabs[subview].id);
  renderShoppingItems();
}

// Menu ⋯ : Réinitialiser la semaine / Vider les achetés.
function setMenuOpen(open) {
  if (!menu || !moreButton) return;
  menu.hidden = !open;
  moreButton.setAttribute("aria-expanded", String(open));
  if (open) {
    const first = menu.querySelector('[role="menuitem"]');
    if (first) first.focus();
  }
}

function initMenu() {
  if (!menu || !moreButton) return;
  moreButton.addEventListener("click", () => setMenuOpen(menu.hidden));
  menu.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    event.stopPropagation(); // Échap ferme le menu, pas la feuille
    setMenuOpen(false);
    moreButton.focus();
  });
  document.addEventListener("click", (event) => {
    if (!menu.hidden && !menu.contains(event.target) && !moreButton.contains(event.target)) setMenuOpen(false);
  });
}

async function resetWeek() {
  setMenuOpen(false);
  if (!confirm("Voulez-vous réinitialiser tous les articles cochés pour cette semaine ?")) return;
  try {
    clearStoredCheckedItems();
    if (banner) banner.hidden = true;
    await resetShoppingList();
    speak("La liste de courses de la semaine a été réinitialisée.");
    await fetchShoppingList();
  } catch (err) {
    showToast(err.message, "error", { title: "Réinitialisation impossible" });
  }
}

async function clearBought() {
  setMenuOpen(false);
  if (!confirm("Voulez-vous vider les articles cochés de la liste d'attente ?")) return;
  try {
    // Passe par Otis : l'action est journalisée, donc annulable depuis l'accueil.
    const res = await postInteract("Vide la liste de courses");
    if (!res.ok) throw new Error(`Nettoyage refusé (erreur ${res.status})`);
    const data = await res.json();
    showToast(data.spoken_response || "Articles nettoyés", "success", { title: "Courses" });
    await fetchShoppingList();
  } catch (err) {
    showToast(err.message, "error", { title: "Nettoyage impossible" });
  }
}

export function initShoppingView() {
  Object.entries(tabs).forEach(([key, tab]) => tab && tab.addEventListener("click", () => selectTab(key)));
  initMenu();
  const resetButton = document.getElementById("btn-reset-shopping");
  const clearButton = document.getElementById("btn-clear-bought");
  if (resetButton) resetButton.addEventListener("click", resetWeek);
  if (clearButton) clearButton.addEventListener("click", clearBought);
}
