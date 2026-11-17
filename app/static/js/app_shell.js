// Coquille de l'app : menu burger, feuilles, barre de saisie unique déplacée dans la feuille ouverte,
// chargement des données d'une section à son ouverture et après une réponse d'Otis.
import { state } from "./config.js";
import { showToastInfo } from "./toast.js";
import { SECTIONS, sectionForSheet, placeholderForSheet, greetingFor, formatLongDate } from "./ui_shell.js";
import { createSheetManager, bindSheetInteractions } from "./sheets.js";
import { scrollConversationToEnd } from "./views/chat_view.js";
import { fetchShoppingList } from "./views/shopping_view.js";
import { loadTasks } from "./views/tasks_view.js";
import { initDuePicker, setDuePickerVisible } from "./views/task_due_picker.js";
import { loadMeals, resetMealsWeek } from "./views/meals_view.js";
import { initSportSheet, loadSport } from "./views/sport/sport_sheet.js";
import { loadSecondBrain, resetSecondBrainFilters } from "./views/second_brain_view.js";
import { loadConversationAuditLogs } from "./views/journal_view.js";
import { loadSettings } from "./views/settings_view.js";
import { initHomeView, loadHome } from "./views/home_view.js";

// Chargement des données d'une section à son ouverture (et après une réponse d'Otis).
function loadSection(section) {
  if (section === "courses") {
    fetchShoppingList();
  } else if (section === "taches") {
    loadTasks();
  } else if (section === "repas") {
    loadMeals();
  } else if (section === "sport") {
    loadSport();
  } else if (section === "second_cerveau") {
    loadSecondBrain();
  } else if (section === "journal") {
    loadConversationAuditLogs();
  } else if (section === "reglages") {
    loadSettings();
  }
}

// Monte la coquille ; retourne le gestionnaire de feuilles et openSection(section) (raccourcis d'URL, réglages).
export function initShell() {
  const manager = createSheetManager({
    getSheet: (id) => document.getElementById(id),
    app: document.getElementById("app-home"),
    drawer: document.getElementById("drawer"),
    backdrop: document.querySelector(".sheet-backdrop"),
    burger: document.getElementById("btn-open-drawer"),
  });
  bindSheetInteractions(manager, document);
  initDuePicker();
  initSportSheet(manager);

  const composer = document.getElementById("query-form");
  const queryInput = document.getElementById("query-input");
  const homeSlot = document.getElementById("composer-home-slot");
  const home = document.getElementById("view-home");
  const drawerItems = document.querySelectorAll(".drawer__item[data-section]");

  const now = new Date();
  const greeting = document.getElementById("topbar-greeting");
  const dateLabel = document.getElementById("topbar-date");
  if (greeting) greeting.textContent = `${greetingFor(now)} Alexis`;
  if (dateLabel) dateLabel.textContent = formatLongDate(now);

  // La feuille du dessus reçoit la barre de saisie (si elle a un emplacement), son placeholder et son contexte.
  manager.onChange((topId) => {
    const section = sectionForSheet(topId);
    const config = SECTIONS[section];
    const topSheet = topId ? document.getElementById(topId) : null;
    const slot = topSheet ? topSheet.querySelector(".composer-slot") : homeSlot;
    if (slot && composer && composer.parentElement !== slot) slot.appendChild(composer);
    if (queryInput) queryInput.placeholder = topId ? placeholderForSheet(topId) : config.placeholder;
    state.uiContext = config.context;
    setDuePickerVisible(section === "taches"); // calendrier de la barre : feuille Tâches seulement
    if (home) home.classList.toggle("active", !topId);
    if (!topId) loadHome(); // retour à l'accueil : les bulles reflètent ce qui a changé dans la feuille
    drawerItems.forEach((item) => {
      if (item.dataset.section === section) item.setAttribute("aria-current", "page");
      else item.removeAttribute("aria-current");
    });
  });

  function openSection(section, trigger = null) {
    const config = SECTIONS[section];
    if (!config) throw new Error(`Section inconnue : « ${section} » (attendu : ${Object.keys(SECTIONS).join(", ")}).`);
    if (!config.sheetId) {
      manager.closeDrawer({ restoreFocus: false });
      manager.closeAll();
      return;
    }
    manager.openSection(config.sheetId, trigger);
    if (section === "repas") resetMealsWeek(); // chaque ouverture repart de la semaine en cours
    if (section === "second_cerveau") resetSecondBrainFilters(); // chaque ouverture repart de « Tout »
    loadSection(section);
  }

  const burger = document.getElementById("btn-open-drawer");
  if (burger) burger.addEventListener("click", () => manager.openDrawer(burger));

  // Menu et bulles de l'accueil : `data-section` ouvre la section ; le focus revient au burger à la fermeture.
  document.addEventListener("click", (e) => {
    const opener = e.target.closest("[data-section]");
    if (!opener) return;
    e.preventDefault();
    const fromDrawer = !!opener.closest(".drawer");
    openSection(opener.dataset.section, fromDrawer ? burger : opener);
  });

  // Feuille Conversation : depuis « Dernières actions » (en-tête ou dernière réponse d'Otis).
  document.addEventListener("click", (e) => {
    const opener = e.target.closest("[data-open-conversation]");
    if (!opener) return;
    manager.openSection("view-conversation", opener);
    scrollConversationToEnd(); // le fil s'ouvre sur le dernier message
  });
  initHomeView();

  // Réponse d'Otis : sur l'accueil, les dernières actions se mettent à jour ; sur une feuille
  // (hors Conversation, où elle s'affiche déjà) : toast + rafraîchissement de la section.
  window.addEventListener("otis-reply", (e) => {
    const topId = manager.topSheetId();
    if (!topId) {
      loadHome();
      return;
    }
    if (topId === "view-conversation") return;
    const text = e.detail && e.detail.text;
    if (text) showToastInfo(text, "Otis");
    loadSection(sectionForSheet(topId));
  });

  return { manager, openSection };
}
