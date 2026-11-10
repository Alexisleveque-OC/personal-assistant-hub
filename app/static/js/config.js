// Configuration, État global et Persistance locale pour la PWA
import { resolveTheme } from "./ui_shell.js";

const prefersDarkScheme = () =>
  typeof window !== "undefined" && !!window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;

export const state = {
  apiKey: localStorage.getItem("pah_api_key") || "",
  ttsEnabled: localStorage.getItem("pah_tts_enabled") !== "false",
  selectedVoiceUri: localStorage.getItem("pah_voice_uri") || "",
  // Choix enregistré (bascule du menu), sinon thème du système.
  currentTheme: resolveTheme(localStorage.getItem("pah_theme"), prefersDarkScheme()),
  uiContext: "accueil", // feuille ouverte, transmise à Otis (voir SECTIONS dans ui_shell.js)
  currentShoppingSubview: "cette-semaine", // 'cette-semaine' | 'liste-attente'
  currentMealSubview: "today", // 'today' | 'week'
  currentSportSubview: "today", // 'today' | 'dashboard' | 'gamification'
  currentSportScale: "week", // 'week' | 'month' | 'year'
  currentSportMetric: "volume", // graphique du dashboard : 'volume' | 'allure' | 'charge' | 'securite'
  cachedShoppingData: { waiting_list: [], current_week_items: [], rayons_order: null },
  vadSilenceMs: parseInt(localStorage.getItem("pah_vad_silence_ms") || "2000", 10),
  pushToTalk: localStorage.getItem("pah_push_to_talk") === "true",
  wakeWordEnabled: localStorage.getItem("pah_wake_word_enabled") === "true",
  wakeWordCustomVariants: JSON.parse(localStorage.getItem("pah_wake_word_custom_variants") || "[]"),
};

export function getStoredCheckedItems() {
  try {
    return JSON.parse(localStorage.getItem("pah_checked_cette_semaine") || "[]");
  } catch (e) {
    return [];
  }
}

export function setStoredCheckedItems(items) {
  localStorage.setItem("pah_checked_cette_semaine", JSON.stringify(items));
}

export function clearStoredCheckedItems() {
  localStorage.removeItem("pah_checked_cette_semaine");
}

// `persist` : seul un choix explicite (bascule du menu) est enregistré ; sinon le thème suit le système.
export function applyTheme(theme, { persist = true } = {}) {
  state.currentTheme = theme;
  document.documentElement.setAttribute("data-theme", theme);
  if (persist) localStorage.setItem("pah_theme", theme);

  const themeSwitch = document.getElementById("theme-switch");
  if (themeSwitch) themeSwitch.checked = theme === "dark";

  const themeIconSun = document.getElementById("theme-icon-sun");
  const themeIconMoon = document.getElementById("theme-icon-moon");
  const btnThemeToggle = document.getElementById("btn-theme-toggle");

  if (themeIconSun && themeIconMoon) {
    if (theme === "dark") {
      themeIconSun.style.display = "block";
      themeIconMoon.style.display = "none";
      if (btnThemeToggle) btnThemeToggle.title = "Passer au thème clair (Cocooning)";
    } else {
      themeIconSun.style.display = "none";
      themeIconMoon.style.display = "block";
      if (btnThemeToggle) btnThemeToggle.title = "Passer au thème sombre (Botanique)";
    }
  }

  const metaThemeColor = document.querySelector('meta[name="theme-color"]');
  if (metaThemeColor) {
    metaThemeColor.setAttribute("content", theme === "dark" ? "#141416" : "#F6F4EF"); // --bg de hub.css
  }
}

export function initTheme() {
  applyTheme(state.currentTheme, { persist: false });
  const themeSwitch = document.getElementById("theme-switch");
  if (themeSwitch) {
    themeSwitch.addEventListener("change", (e) => applyTheme(e.target.checked ? "dark" : "light"));
  }
  const btnThemeToggle = document.getElementById("btn-theme-toggle");
  if (btnThemeToggle) {
    btnThemeToggle.addEventListener("click", () => {
      const nextTheme = state.currentTheme === "dark" ? "light" : "dark";
      applyTheme(nextTheme);
    });
  }
}

export function getActiveSessionId() {
  const SESSION_TTL_MS = 24 * 60 * 60 * 1000; // 24 heures (continuité sans coupure intempestive)
  const now = Date.now();
  let sessionId = localStorage.getItem("pah_session_id");
  const lastActive = parseInt(localStorage.getItem("pah_session_timestamp") || "0", 10);

  if (!sessionId || (now - lastActive) > SESSION_TTL_MS) {
    const randomPart = Math.random().toString(36).substring(2, 9);
    sessionId = "pwa_" + now.toString(36) + "_" + randomPart;
    localStorage.setItem("pah_session_id", sessionId);
  }
  localStorage.setItem("pah_session_timestamp", now.toString());
  return sessionId;
}

export function resetActiveSessionId() {
  localStorage.removeItem("pah_session_id");
  localStorage.removeItem("pah_session_timestamp");
  return getActiveSessionId();
}

