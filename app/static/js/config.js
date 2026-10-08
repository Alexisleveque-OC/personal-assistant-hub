// Configuration, État global et Persistance locale pour la PWA
export const state = {
  apiKey: localStorage.getItem("pah_api_key") || "",
  ttsEnabled: localStorage.getItem("pah_tts_enabled") !== "false",
  selectedVoiceUri: localStorage.getItem("pah_voice_uri") || "",
  currentTheme: localStorage.getItem("pah_theme") || "light",
  currentShoppingSubview: "cette-semaine", // 'cette-semaine' | 'liste-attente'
  currentMealSubview: "today", // 'today' | 'week'
  currentSportSubview: "today", // 'today' | 'dashboard' | 'gamification'
  currentSportScale: "week", // 'week' | 'month' | 'year'
  cachedShoppingData: { waiting_list: [], current_week_items: [], rayons_order: null },
  vadSilenceMs: parseInt(localStorage.getItem("pah_vad_silence_ms") || "2000", 10),
  pushToTalk: localStorage.getItem("pah_push_to_talk") === "true",
  wakeWordEnabled: localStorage.getItem("pah_wake_word_enabled") === "true",
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

export function applyTheme(theme) {
  state.currentTheme = theme;
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("pah_theme", theme);

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
    metaThemeColor.setAttribute("content", theme === "dark" ? "#0d1721" : "#f4f3ef");
  }
}

export function initTheme() {
  applyTheme(state.currentTheme);
  const btnThemeToggle = document.getElementById("btn-theme-toggle");
  if (btnThemeToggle) {
    btnThemeToggle.addEventListener("click", () => {
      const nextTheme = state.currentTheme === "dark" ? "light" : "dark";
      applyTheme(nextTheme);
    });
  }
}
