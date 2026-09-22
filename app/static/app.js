// Personal Assistant Hub - Mobile PWA Engine

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const chatStream = document.getElementById("chat-stream");
  const queryForm = document.getElementById("query-form");
  const queryInput = document.getElementById("query-input");
  const micWrapper = document.getElementById("mic-wrapper");
  const micBtn = document.getElementById("mic-btn");
  const voiceBarArea = document.getElementById("voice-bar-area");
  const interimTranscript = document.getElementById("interim-transcript");
  const btnTtsToggle = document.getElementById("btn-tts-toggle");
  const btnSettings = document.getElementById("btn-settings");
  const settingsModal = document.getElementById("settings-modal");
  const btnCloseSettings = document.getElementById("btn-close-settings");
  const btnSaveSettings = document.getElementById("btn-save-settings");
  const apiKeyInput = document.getElementById("api-key-input");
  const shoppingListContainer = document.getElementById("shopping-list-container");
  const btnClearBought = document.getElementById("btn-clear-bought");
  const mealContainer = document.getElementById("meal-container");

  // Nav items
  const navItems = document.querySelectorAll(".nav-item");
  const views = {
    chat: document.getElementById("view-chat"),
    shopping: document.getElementById("view-shopping"),
    meals: document.getElementById("view-meals")
  };

  // State
  let apiKey = localStorage.getItem("pah_api_key") || "";
  let ttsEnabled = localStorage.getItem("pah_tts_enabled") !== "false";
  let isRecording = false;
  let recognition = null;

  // Initialize UI State
  updateTtsButtonState();
  if (apiKeyInput) apiKeyInput.value = apiKey;

  // Register PWA Service Worker
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js")
      .then(() => console.log("[PWA] Service Worker registered"))
      .catch((err) => console.warn("[PWA] Service Worker registration failed:", err));
  }

  // Speech Recognition (STT) Setup
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = "fr-FR";
    recognition.interimResults = true;
    recognition.continuous = false;

    recognition.onstart = () => {
      isRecording = true;
      micWrapper.classList.add("recording");
      voiceBarArea.classList.add("active");
      interimTranscript.textContent = "Je vous écoute...";
    };

    recognition.onresult = (event) => {
      let finalTranscript = "";
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript;
        } else {
          interim += event.results[i][0].transcript;
        }
      }
      interimTranscript.textContent = interim || finalTranscript || "Je vous écoute...";
      if (finalTranscript.trim()) {
        sendInteraction(finalTranscript.trim());
      }
    };

    recognition.onerror = (event) => {
      console.warn("[STT Error]", event.error);
      stopRecording();
      if (event.error === "not-allowed") {
        appendAssistantMessage("Accès au microphone refusé. Veuillez autoriser le micro dans votre navigateur.");
      }
    };

    recognition.onend = () => {
      stopRecording();
    };
  }

  function startRecording() {
    if (!recognition) {
      alert("La reconnaissance vocale n'est pas supportée par votre navigateur actuel. Vous pouvez saisir votre message au clavier.");
      return;
    }
    try {
      recognition.start();
    } catch (e) {
      console.warn("Recognition already started or error:", e);
    }
  }

  function stopRecording() {
    isRecording = false;
    if (micWrapper) micWrapper.classList.remove("recording");
    if (voiceBarArea) voiceBarArea.classList.remove("active");
    if (interimTranscript) interimTranscript.textContent = "";
  }

  if (micBtn) {
    micBtn.addEventListener("click", () => {
      if (isRecording) {
        if (recognition) recognition.stop();
        stopRecording();
      } else {
        startRecording();
      }
    });
  }

  // TTS Output
  function speak(text) {
    if (!ttsEnabled || !("speechSynthesis" in window) || !text) return;
    window.speechSynthesis.cancel();
    const cleanText = text.replace(/[*_#]/g, "");
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = "fr-FR";
    utterance.rate = 1.05;
    utterance.pitch = 1.0;
    window.speechSynthesis.speak(utterance);
  }

  function updateTtsButtonState() {
    if (!btnTtsToggle) return;
    if (ttsEnabled) {
      btnTtsToggle.classList.add("active");
      btnTtsToggle.title = "Voix activée (cliquez pour couper)";
    } else {
      btnTtsToggle.classList.remove("active");
      btnTtsToggle.title = "Voix coupée (cliquez pour activer)";
    }
  }

  if (btnTtsToggle) {
    btnTtsToggle.addEventListener("click", () => {
      ttsEnabled = !ttsEnabled;
      localStorage.setItem("pah_tts_enabled", ttsEnabled ? "true" : "false");
      updateTtsButtonState();
      if (!ttsEnabled && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    });
  }

  // Settings Modal (API Key)
  if (btnSettings) {
    btnSettings.addEventListener("click", () => {
      if (apiKeyInput) apiKeyInput.value = apiKey;
      if (settingsModal) settingsModal.classList.add("active");
    });
  }

  if (btnCloseSettings) {
    btnCloseSettings.addEventListener("click", () => {
      if (settingsModal) settingsModal.classList.remove("active");
    });
  }

  if (btnSaveSettings) {
    btnSaveSettings.addEventListener("click", () => {
      apiKey = apiKeyInput ? apiKeyInput.value.trim() : "";
      localStorage.setItem("pah_api_key", apiKey);
      if (settingsModal) settingsModal.classList.remove("active");
      appendAssistantMessage("Clé API enregistrée avec succès !");
    });
  }

  // Navigation Switcher
  navItems.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetView = btn.getAttribute("data-view");
      navItems.forEach((n) => n.classList.remove("active"));
      btn.classList.add("active");

      Object.keys(views).forEach((k) => {
        if (views[k]) views[k].classList.toggle("active", k === targetView);
      });

      if (targetView === "shopping") {
        loadShoppingList();
      } else if (targetView === "meals") {
        loadMealPlan();
      }
    });
  });

  // Query Form
  if (queryForm) {
    queryForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const val = queryInput.value.trim();
      if (val) {
        queryInput.value = "";
        sendInteraction(val);
      }
    });
  }

  // Suggestion Chips
  document.querySelectorAll(".chip-btn").forEach((chip) => {
    chip.addEventListener("click", () => {
      const text = chip.getAttribute("data-query") || chip.textContent.trim();
      sendInteraction(text);
    });
  });

  // Core API interaction
  async function sendInteraction(text) {
    appendUserMessage(text);
    const headers = { "Content-Type": "application/json" };
    if (apiKey) {
      headers["X-API-Key"] = apiKey;
    }

    try {
      const res = await fetch("/api/v1/interact", {
        method: "POST",
        headers: headers,
        body: JSON.stringify({ query: text })
      });

      if (res.status === 401) {
        appendAssistantMessage("Erreur d'authentification (401) : Clé API manquante ou invalide. Veuillez cliquer sur la roue crantée en haut à droite pour renseigner votre clé.");
        return;
      }

      if (!res.ok) {
        appendAssistantMessage(`Erreur serveur (${res.status}). Veuillez réessayer.`);
        return;
      }

      const data = await res.json();
      appendAssistantMessage(data.spoken_response);
      speak(data.spoken_response);
    } catch (err) {
      appendAssistantMessage("Impossible de joindre le serveur. Vérifiez votre connexion.");
    }
  }

  function appendUserMessage(text) {
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble user";
    bubble.textContent = text;
    chatStream.appendChild(bubble);
    bubble.scrollIntoView({ behavior: "smooth" });
  }

  function appendAssistantMessage(text) {
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble assistant";

    const header = document.createElement("div");
    header.className = "bubble-header";
    header.innerHTML = `<span>Assistant Hub</span>
      <button class="btn-tts" title="Réécouter">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
          <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
        </svg>
      </button>`;

    const content = document.createElement("div");
    content.className = "bubble-content";
    content.textContent = text;

    bubble.appendChild(header);
    bubble.appendChild(content);
    chatStream.appendChild(bubble);

    const btnReplay = header.querySelector(".btn-tts");
    btnReplay.addEventListener("click", () => speak(text));

    bubble.scrollIntoView({ behavior: "smooth" });
  }

  // Load Shopping List View
  async function loadShoppingList() {
    if (!shoppingListContainer) return;
    shoppingListContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted)">Chargement de la liste de courses...</div>';

    const headers = { "Content-Type": "application/json" };
    if (apiKey) headers["X-API-Key"] = apiKey;

    try {
      const res = await fetch("/api/v1/interact", {
        method: "POST",
        headers: headers,
        body: JSON.stringify({ query: "Donne-moi la liste de courses" })
      });

      if (!res.ok) {
        shoppingListContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--accent-rose)">Impossible de charger la liste de courses.</div>';
        return;
      }

      const payload = await res.json();
      const waitingList = (payload.data && payload.data.waiting_list) || [];
      const currentWeek = (payload.data && payload.data.current_week_items) || [];

      if (waitingList.length === 0 && currentWeek.length === 0) {
        shoppingListContainer.innerHTML = `
          <div style="text-align:center; padding:40px 20px; color:var(--text-muted)">
            <svg viewBox="0 0 24 24" width="48" height="48" fill="currentColor" style="opacity:0.4; margin-bottom:12px;">
              <path d="M7 18c-1.1 0-1.99.9-1.99 2S5.9 22 7 22s2-.9 2-2-.9-2-2-2zM1 2v2h2l3.6 7.59-1.35 2.45c-.16.28-.25.61-.25.96 0 1.1.9 2 2 2h12v-2H7.42c-.14 0-.25-.11-.25-.25l.03-.12.9-1.63h7.45c.75 0 1.41-.41 1.75-1.03l3.58-6.49c.08-.14.12-.31.12-.48 0-.55-.45-1-1-1H5.21l-.94-2H1zm16 16c-1.1 0-1.99.9-1.99 2s.89 2 1.99 2 2-.9 2-2-.9-2-2-2z"/>
            </svg>
            <p>Votre liste de courses est complètement vide !</p>
          </div>`;
        return;
      }

      // Group items by Rayon
      const grouped = {};
      waitingList.forEach((it) => {
        const rayon = it.rayon || "Divers";
        if (!grouped[rayon]) grouped[rayon] = [];
        grouped[rayon].push({ name: it.item, is_bought: it.is_bought, source: "waiting_list" });
      });

      currentWeek.forEach((it) => {
        const rayon = it.rayon || "Divers";
        if (!grouped[rayon]) grouped[rayon] = [];
        grouped[rayon].push({ name: it.name, is_bought: it.checked, source: "current_week" });
      });

      let html = "";
      Object.keys(grouped).sort().forEach((rayon) => {
        const items = grouped[rayon];
        html += `
          <div class="rayon-card">
            <div class="rayon-card-header">
              <span>${rayon}</span>
              <span>${items.length}</span>
            </div>
            <div class="rayon-items">
        `;
        items.forEach((item) => {
          const checkedClass = item.is_bought ? "checked" : "";
          html += `
            <div class="shopping-item-row ${checkedClass}" data-item="${encodeURIComponent(item.name)}">
              <div class="custom-checkbox">
                <svg viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
              </div>
              <span class="item-label">${item.name}</span>
            </div>
          `;
        });
        html += `</div></div>`;
      });

      shoppingListContainer.innerHTML = html;

      // Add click listener to mark bought
      shoppingListContainer.querySelectorAll(".shopping-item-row").forEach((row) => {
        row.addEventListener("click", async () => {
          const itemName = decodeURIComponent(row.getAttribute("data-item"));
          const wasChecked = row.classList.contains("checked");
          row.classList.toggle("checked");

          if (!wasChecked) {
            // Call API to mark item as bought
            try {
              await fetch("/api/v1/interact", {
                method: "POST",
                headers: headers,
                body: JSON.stringify({ query: `J'ai acheté ${itemName}` })
              });
            } catch (e) {
              console.warn("Failed to mark item bought on server:", e);
            }
          }
        });
      });
    } catch (err) {
      shoppingListContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--accent-rose)">Erreur de connexion lors du chargement des courses.</div>';
    }
  }

  // Clear Bought Items Action
  if (btnClearBought) {
    btnClearBought.addEventListener("click", async () => {
      if (!confirm("Voulez-vous supprimer les articles achetés de la liste ?")) return;
      const headers = { "Content-Type": "application/json" };
      if (apiKey) headers["X-API-Key"] = apiKey;

      try {
        const res = await fetch("/api/v1/interact", {
          method: "POST",
          headers: headers,
          body: JSON.stringify({ query: "Vide la liste de courses" })
        });
        const data = await res.json();
        alert(data.spoken_response || "Articles nettoyés");
        loadShoppingList();
      } catch (err) {
        alert("Erreur lors du nettoyage de la liste");
      }
    });
  }

  // Load Meal Plan View
  async function loadMealPlan() {
    if (!mealContainer) return;
    mealContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted)">Chargement du menu...</div>';

    const headers = { "Content-Type": "application/json" };
    if (apiKey) headers["X-API-Key"] = apiKey;

    try {
      const res = await fetch("/api/v1/interact", {
        method: "POST",
        headers: headers,
        body: JSON.stringify({ query: "Qu'est-ce qu'on mange aujourd'hui ?" })
      });

      if (!res.ok) {
        mealContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--accent-rose)">Impossible de charger les repas.</div>';
        return;
      }

      const payload = await res.json();
      const plan = (payload.data && payload.data.plan) || {};
      const dateStr = plan.date_str || "Aujourd'hui";
      const dayName = plan.day_name || "Ce jour";
      const lunch = plan.lunch || "Non défini";
      const dinner = plan.dinner || "Non défini";

      mealContainer.innerHTML = `
        <div class="meal-hero-card">
          <span class="meal-date-badge">${dayName} • ${dateStr}</span>
          <div class="meal-block">
            <div class="meal-time-label">Midi (Déjeuner)</div>
            <div class="meal-dish-name">${lunch}</div>
          </div>
          <div class="meal-block" style="margin-top:20px;">
            <div class="meal-time-label">Soir (Dîner)</div>
            <div class="meal-dish-name">${dinner}</div>
          </div>
        </div>

        <div style="margin-top:24px;">
          <h3 class="section-title" style="margin-bottom:12px;">Actions rapides repas</h3>
          <div style="display:flex; flex-direction:column; gap:10px;">
            <button class="chip-btn" style="text-align:left; padding:12px 16px;" data-query="Qu'est-ce qu'on mange demain midi ?">
              🍴 Qu'est-ce qu'on mange demain midi ?
            </button>
            <button class="chip-btn" style="text-align:left; padding:12px 16px;" data-query="Qu'est-ce qu'on mange demain soir ?">
              🌙 Qu'est-ce qu'on mange demain soir ?
            </button>
            <button class="chip-btn" style="text-align:left; padding:12px 16px;" data-query="Quels sont les ingrédients pour le risotto de quinoa ?">
              📖 Ingrédients d'une recette
            </button>
          </div>
        </div>
      `;

      mealContainer.querySelectorAll(".chip-btn").forEach((chip) => {
        chip.addEventListener("click", () => {
          const q = chip.getAttribute("data-query");
          // Switch to chat tab and send query
          document.querySelector('.nav-item[data-view="chat"]').click();
          sendInteraction(q);
        });
      });
    } catch (err) {
      mealContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--accent-rose)">Erreur de connexion lors du chargement du menu.</div>';
    }
  }

  // URL query params handling (e.g. from PWA shortcuts: /app?action=meal_today)
  const urlParams = new URLSearchParams(window.location.search);
  const actionParam = urlParams.get("action");
  if (actionParam === "shopping_list") {
    document.querySelector('.nav-item[data-view="shopping"]').click();
  } else if (actionParam === "meal_today") {
    document.querySelector('.nav-item[data-view="meals"]').click();
  }
});
