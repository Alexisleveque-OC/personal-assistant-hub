// Personal Assistant Hub - PWA Entrypoint & Modular Orchestrator
import { state, initTheme } from "./js/config.js";
import { audioFocusManager } from "./js/audio_focus.js";
import {
  SpeechRecognition,
  initSpeechRecognition,
  setWakeWordEnabled,
  toggleWakeWord,
  startWakeWordCalibration,
  updateWakeWordIndicator,
  addCustomWakeVariant,
  removeCustomWakeVariant,
} from "./js/speech.js";
import { showToastSuccess, showToastInfo } from "./js/toast.js";
import { initChatView, sendInteraction, sendAudioInteraction, appendAssistantMessage, handleOfflineSyncedResponse } from "./js/views/chat_view.js";
import { initShoppingView, fetchShoppingList } from "./js/views/shopping_view.js";
import { initTasksView, loadTasks } from "./js/views/tasks_view.js";
import { initDuePicker, setDuePickerVisible } from "./js/views/task_due_picker.js";
import { initMealsView, loadMeals, resetMealsWeek } from "./js/views/meals_view.js";
import { initSportView } from "./js/views/sport_view.js";
import { initSportSheet, loadSport, openTrophies } from "./js/views/sport/sport_sheet.js";
import { initSecondBrainView, loadSecondBrain, resetSecondBrainFilters } from "./js/views/second_brain_view.js";
import { loadConversationAuditLogs } from "./js/views/journal_view.js";
import { initSettingsView, loadSettings } from "./js/views/settings_view.js";
import { initOfflineSync, syncOutbox } from "./js/offline_outbox.js";
import { SECTIONS, sectionForSheet, placeholderForSheet, sectionForAction, greetingFor, formatLongDate } from "./js/ui_shell.js";
import { createSheetManager, bindSheetInteractions } from "./js/sheets.js";
import { initHomeView, loadHome } from "./js/views/home_view.js";

// Export / Référence SpeechRecognition pour les vérifications de compatibilité
export { SpeechRecognition };

document.addEventListener("DOMContentLoaded", () => {
  // 1. Initialisation Audio Focus (Mode Ambient non-intrusif) & Thème
  audioFocusManager.initAudioSession();
  initTheme();

  // 2. Éléments globaux
  const btnTtsToggle = document.getElementById("btn-tts-toggle");
  // (Réglages & voix : feuille dédiée, voir js/views/settings_view.js.)

  // 4. Initialisation TTS (Bouton switch)
  function updateTtsButtonState() {
    if (!btnTtsToggle) return;
    btnTtsToggle.setAttribute("aria-pressed", state.ttsEnabled ? "true" : "false");
    if (state.ttsEnabled) {
      btnTtsToggle.classList.add("active");
      btnTtsToggle.title = "Voix activée (cliquez pour couper)";
    } else {
      btnTtsToggle.classList.remove("active");
      btnTtsToggle.title = "Voix coupée (cliquez pour activer)";
    }
  }
  updateTtsButtonState();

  if (btnTtsToggle) {
    btnTtsToggle.addEventListener("click", () => {
      state.ttsEnabled = !state.ttsEnabled;
      localStorage.setItem("pah_tts_enabled", state.ttsEnabled ? "true" : "false");
      updateTtsButtonState();
      if (!state.ttsEnabled && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    });
  }

  // 6. Reconnaissance Vocale Haute-Fidélité (VAD & MediaRecorder Audio)
  initSpeechRecognition(
    (transcript) => sendInteraction(transcript),
    () => appendAssistantMessage("Accès au microphone refusé. Veuillez autoriser le micro dans votre navigateur."),
    (audioBlob) => sendAudioInteraction(audioBlob)
  );

  // 7. Initialisation des Vues Métier
  initChatView();
  initSecondBrainView();
  initShoppingView();
  initTasksView();
  initMealsView();
  initSportView();

  // 8. Navigation : menu burger + feuilles (refonte UX, remplace la barre d'onglets du bas)
  const shell = initShell();

  // 9. Réglages & voix : feuille dédiée (ancienne modale) ; la croix ferme sans enregistrer.
  initSettingsView({ close: () => shell.manager.closeTop() });

  // 9.1 Module de Calibrage Wake-Word In-App
  const btnStartCalibration = document.getElementById("btn-start-calibration");
  const calibrationStatus = document.getElementById("calibration-status");
  const calibrationResults = document.getElementById("calibration-results");
  const btnAddCustomWake = document.getElementById("btn-add-custom-wake-variant");
  const inputCustomWake = document.getElementById("input-custom-wake-variant");

  function renderCalibrationChips() {
    if (!calibrationResults) return;
    calibrationResults.innerHTML = "";
    const list = state.wakeWordCustomVariants || [];
    if (list.length === 0) {
      calibrationResults.innerHTML = '<span style="font-size:0.75rem; color:var(--color-text-secondary);">Variantes par défaut actives. Ajoutez vos prononciations ci-dessus.</span>';
      return;
    }
    list.forEach((v) => {
      const chip = document.createElement("span");
      chip.className = "calibration-chip";
      chip.style.cssText = "display:inline-flex; align-items:center; gap:6px; background:var(--color-surface); border:1px solid var(--color-border); border-radius:12px; padding:3px 8px; font-size:0.75rem;";
      chip.innerHTML = `<span>✓ ${v}</span>`;
      const btnDel = document.createElement("button");
      btnDel.type = "button";
      btnDel.textContent = "×";
      btnDel.title = "Supprimer cette variante";
      btnDel.style.cssText = "background:none; border:none; color:var(--color-text-secondary); cursor:pointer; font-size:0.85rem; padding:0 2px; line-height:1;";
      btnDel.addEventListener("click", () => {
        removeCustomWakeVariant(v);
        renderCalibrationChips();
      });
      chip.appendChild(btnDel);
      calibrationResults.appendChild(chip);
    });
  }

  if (btnAddCustomWake && inputCustomWake) {
    const handleAddManual = () => {
      const val = inputCustomWake.value.trim();
      if (!val) return;
      addCustomWakeVariant(val);
      inputCustomWake.value = "";
      renderCalibrationChips();
      if (calibrationStatus) calibrationStatus.textContent = `Ajouté : « ${val} »`;
    };
    btnAddCustomWake.addEventListener("click", handleAddManual);
    inputCustomWake.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        handleAddManual();
      }
    });
  }

  if (btnStartCalibration) {
    btnStartCalibration.addEventListener("click", () => {
      if (calibrationStatus) calibrationStatus.textContent = "Écoute en cours... Dites « Otis »";
      startWakeWordCalibration(
        (status, msg) => {
          if (calibrationStatus) calibrationStatus.textContent = msg;
        },
        (success, resultText) => {
          if (success) {
            if (calibrationStatus) calibrationStatus.textContent = `Enregistré : « ${resultText} »`;
            renderCalibrationChips();
          } else {
            if (calibrationStatus) calibrationStatus.textContent = `Échec : ${resultText}`;
          }
        }
      );
    });
  }

  // Refonte UX : l'indicateur est dans l'interrupteur « Mains-libres » du menu (un <label>) ; c'est la case qui bascule,
  // un écouteur de clic sur l'indicateur basculerait une seconde fois.
  // const wakeWordIndicator = document.getElementById("wake-word-indicator");
  // if (wakeWordIndicator) {
  //   wakeWordIndicator.addEventListener("click", () => {
  //     const isNowEnabled = toggleWakeWord();
  //     if (isNowEnabled) {
  //       showToastInfo("Mains-libres 'Otis' activé (détection sur le téléphone, la musique n'est pas coupée).", "Otis à l'écoute");
  //     } else {
  //       showToastSuccess("Mode au clic activé : micro coupé, votre musique joue à 100% de volume.", "Micro au clic");
  //     }
  //   });
  // }
  const wakeWordSwitch = document.getElementById("wake-word-switch");
  if (wakeWordSwitch) {
    wakeWordSwitch.addEventListener("change", (e) => {
      setWakeWordEnabled(e.target.checked);
      if (e.target.checked) {
        showToastInfo("Mains-libres 'Otis' activé (détection sur le téléphone, la musique n'est pas coupée).", "Otis à l'écoute");
      } else {
        showToastSuccess("Mode au clic activé : micro coupé, votre musique joue à 100% de volume.", "Micro au clic");
      }
    });
  }

  // (Interrupteur « Mains-libres » de la feuille Réglages : voir settings_view.js.)

  // Initialisation du statut visuel du Wake-Word
  updateWakeWordIndicator();

  // 10. Gestion des raccourcis d'URL (?action=...) : ouvrent la feuille correspondante
  const shortcut = sectionForAction(new URLSearchParams(window.location.search).get("action"));
  if (shortcut) {
    shell.openSection(shortcut.section);
    if (shortcut.subview === "gamification") openTrophies();
  }

  // 11. Enregistrement PWA Service Worker
  if ("serviceWorker" in navigator) {
    let refreshing = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (!refreshing) {
        refreshing = true;
        window.location.reload();
      }
    });

    navigator.serviceWorker.register("/sw.js")
      .then((reg) => {
        console.log("[PWA] Service Worker registered");
        reg.update();
      })
      .catch((err) => console.warn("[PWA] Service Worker registration failed:", err));
  }

  // 12. Initialisation File d'Attente Hors-Ligne & Synchronisation PWA
  const outboxIndicator = document.getElementById("offline-outbox-indicator");
  if (outboxIndicator) {
    outboxIndicator.addEventListener("click", () => {
      syncOutbox();
    });
  }
  initOfflineSync((item, data) => {
    handleOfflineSyncedResponse(item, data);
  });
});

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

// Coquille de l'app : menu, feuilles, barre de saisie unique déplacée dans la feuille ouverte.
function initShell() {
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
    if (opener) manager.openSection("view-conversation", opener);
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
