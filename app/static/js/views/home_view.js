// Accueil (refonte UX) : « Dernières actions » (+ dernière réponse d'Otis), 4 bulles et compteurs du menu.
// Chaque bloc se charge indépendamment : une source en panne n'empêche pas les autres de s'afficher.
import {
  fetchRecentActions,
  fetchShoppingData,
  fetchWeekMeals,
  fetchSportTodayData,
  fetchTasks,
  fetchSecondBrainStats,
} from "../api.js";
import { getActiveSessionId, getStoredCheckedItems } from "../config.js";
import { getStoredChatHistory, sendInteraction } from "./chat_view.js";
import {
  shoppingSummary, nextTask, tonightMeal, sportOfTheDay, actionTime, lastAssistantReply,
} from "../home_model.js";

let loading = null; // un seul chargement à la fois (ouverture, retour à l'accueil, réponse d'Otis)

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderBubble(section, { value, foot }, footAccent = false) {
  const bubble = document.getElementById(`bubble-${section}`);
  if (!bubble) return;
  bubble.querySelector(".bubble__value").textContent = value;
  const footEl = bubble.querySelector(".bubble__foot");
  footEl.textContent = foot || "";
  footEl.classList.toggle("bubble__foot--accent", footAccent && !!foot);
}

function renderBubbleError(section, err) {
  console.warn(`[Accueil] Bulle « ${section} » indisponible :`, err);
  renderBubble(section, { value: "—", foot: "Indisponible" });
}

function setDrawerCount(section, count) {
  const badge = document.getElementById(`drawer-count-${section}`);
  if (badge) badge.textContent = count ? String(count) : "";
}

function renderActivity(actions) {
  const list = document.getElementById("home-activity-list");
  if (!list) return;
  list.replaceChildren();

  const reply = lastAssistantReply(getStoredChatHistory());
  if (reply) {
    const row = el("button", "activity__item activity__item--reply");
    row.type = "button";
    row.setAttribute("data-open-conversation", "");
    row.setAttribute("aria-label", `Dernière réponse d'Otis : ${reply}. Ouvrir la conversation`);
    row.append(el("span", "activity__text", reply));
    list.append(row);
  }

  if (!actions.length) {
    list.append(el("div", "activity__item activity__item--empty", "Aucune action récente."));
    return;
  }
  actions.forEach((action) => {
    const row = el("div", "activity__item");
    row.append(el("span", "activity__text", action.label));
    if (action.undoable) {
      const undo = el("button", "activity__undo", "Annuler");
      undo.type = "button";
      undo.setAttribute("aria-label", `Annuler : ${action.label}`);
      undo.addEventListener("click", () => {
        undo.disabled = true;
        sendInteraction("annule ça"); // même chemin que le toast d'annulation de la conversation
      });
      row.append(undo);
    } else {
      row.append(el("span", "activity__meta", actionTime(action.created_at)));
    }
    list.append(row);
  });
}

async function loadActivity() {
  try {
    const data = await fetchRecentActions(getActiveSessionId());
    renderActivity(data.items || []);
  } catch (err) {
    console.warn("[Accueil] Dernières actions indisponibles :", err);
    renderActivity([]);
    const list = document.getElementById("home-activity-list");
    if (list && list.lastElementChild) list.lastElementChild.textContent = "Dernières actions indisponibles.";
  }
}

async function loadShopping() {
  try {
    const summary = shoppingSummary(await fetchShoppingData(), getStoredCheckedItems());
    renderBubble("courses", summary);
    setDrawerCount("courses", summary.count);
  } catch (err) {
    renderBubbleError("courses", err);
  }
}

async function loadMeals() {
  try {
    const data = await fetchWeekMeals();
    renderBubble("repas", tonightMeal(data.week_plan));
  } catch (err) {
    renderBubbleError("repas", err);
  }
}

async function loadSport() {
  try {
    renderBubble("sport", sportOfTheDay(await fetchSportTodayData()));
  } catch (err) {
    renderBubbleError("sport", err);
  }
}

async function loadTasksBubble() {
  try {
    const data = await fetchTasks();
    const taches = data.taches || [];
    const next = nextTask(taches);
    renderBubble("taches", next, taches.some((t) => t.echeance));
    setDrawerCount("taches", taches.length);
  } catch (err) {
    renderBubbleError("taches", err);
  }
}

async function loadNotesCount() {
  try {
    const stats = await fetchSecondBrainStats();
    setDrawerCount("second_cerveau", Object.values(stats || {}).reduce((sum, n) => sum + (Number(n) || 0), 0));
  } catch (err) {
    console.warn("[Accueil] Nombre de notes actives indisponible :", err);
  }
}

export function loadHome() {
  if (loading) return loading;
  loading = Promise.all([loadActivity(), loadShopping(), loadMeals(), loadSport(), loadTasksBubble(), loadNotesCount()])
    .finally(() => { loading = null; });
  return loading;
}

export function initHomeView() {
  loadHome();
}
