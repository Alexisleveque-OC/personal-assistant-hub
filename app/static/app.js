// Personal Assistant Hub - Mobile PWA Engine (Updated)

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
  const voiceSelect = document.getElementById("voice-select");
  const btnTestVoice = document.getElementById("btn-test-voice");

  // Shopping Elements
  const shoppingListContainer = document.getElementById("shopping-list-container");
  const btnClearBought = document.getElementById("btn-clear-bought");
  const tabCetteSemaine = document.getElementById("tab-cette-semaine");
  const tabListeAttente = document.getElementById("tab-liste-attente");
  const badgeCetteSemaine = document.getElementById("badge-cette-semaine");
  const badgeListeAttente = document.getElementById("badge-liste-attente");

  // Meals Elements
  const mealContainer = document.getElementById("meal-container");
  const tabMealToday = document.getElementById("tab-meal-today");
  const tabMealWeek = document.getElementById("tab-meal-week");

  // Nav Items
  const navItems = document.querySelectorAll(".nav-item");
  const views = {
    chat: document.getElementById("view-chat"),
    shopping: document.getElementById("view-shopping"),
    meals: document.getElementById("view-meals")
  };

  // State
  let apiKey = localStorage.getItem("pah_api_key") || "";
  let ttsEnabled = localStorage.getItem("pah_tts_enabled") !== "false";
  let selectedVoiceUri = localStorage.getItem("pah_voice_uri") || "";
  let isRecording = false;
  let recognition = null;
  let currentShoppingSubview = "cette-semaine"; // 'cette-semaine' | 'liste-attente'
  let currentMealSubview = "today"; // 'today' | 'week'
  let cachedShoppingData = { waiting_list: [], current_week_items: [] };
  let frenchVoices = [];

  // Initialize UI State
  updateTtsButtonState();
  if (apiKeyInput) apiKeyInput.value = apiKey;

  // Register PWA Service Worker
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js")
      .then(() => console.log("[PWA] Service Worker registered"))
      .catch((err) => console.warn("[PWA] Service Worker registration failed:", err));
  }

  // --- Voice Synthesis (TTS) & Voice Catalog ---
  function populateVoiceList() {
    if (!("speechSynthesis" in window) || !voiceSelect) return;
    const allVoices = window.speechSynthesis.getVoices();
    frenchVoices = allVoices.filter((v) => v.lang.startsWith("fr"));

    voiceSelect.innerHTML = "";
    if (frenchVoices.length === 0) {
      const opt = document.createElement("option");
      opt.textContent = "Voix française par défaut du système";
      opt.value = "";
      voiceSelect.appendChild(opt);
      return;
    }

    // Sort voices: natural / Google / premium first
    frenchVoices.sort((a, b) => {
      const aScore = (a.name.includes("Google") || a.name.includes("Natural")) ? 1 : 0;
      const bScore = (b.name.includes("Google") || b.name.includes("Natural")) ? 1 : 0;
      return bScore - aScore;
    });

    let matched = false;
    frenchVoices.forEach((voice) => {
      const option = document.createElement("option");
      option.value = voice.voiceURI;
      option.textContent = `${voice.name} (${voice.lang})`;
      if (voice.voiceURI === selectedVoiceUri) {
        option.selected = true;
        matched = true;
      }
      voiceSelect.appendChild(option);
    });

    if (!matched && frenchVoices.length > 0) {
      voiceSelect.selectedIndex = 0;
      selectedVoiceUri = frenchVoices[0].voiceURI;
    }
  }

  populateVoiceList();
  if ("speechSynthesis" in window && window.speechSynthesis.onvoiceschanged !== undefined) {
    window.speechSynthesis.onvoiceschanged = populateVoiceList;
  }

  if (btnTestVoice) {
    btnTestVoice.addEventListener("click", () => {
      const chosenUri = voiceSelect ? voiceSelect.value : "";
      speak("Bonjour ! Voici un exemple avec la voix sélectionnée pour votre assistant personnel.", chosenUri);
    });
  }

  function speak(text, overrideVoiceUri = null) {
    if (!ttsEnabled || !("speechSynthesis" in window) || !text) return;
    window.speechSynthesis.cancel();
    const cleanText = text.replace(/[*_#]/g, "");
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = "fr-FR";
    utterance.rate = 1.02;
    utterance.pitch = 1.0;

    const uriToUse = overrideVoiceUri || selectedVoiceUri;
    if (uriToUse && frenchVoices.length > 0) {
      const foundVoice = frenchVoices.find((v) => v.voiceURI === uriToUse);
      if (foundVoice) utterance.voice = foundVoice;
    }
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

  // --- Speech Recognition (STT) ---
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = "fr-FR";
    recognition.interimResults = true;
    recognition.continuous = false;

    recognition.onstart = () => {
      isRecording = true;
      if (micWrapper) micWrapper.classList.add("recording");
      if (voiceBarArea) voiceBarArea.classList.add("active");
      if (interimTranscript) interimTranscript.textContent = "Je vous écoute...";
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
      if (interimTranscript) interimTranscript.textContent = interim || finalTranscript || "Je vous écoute...";
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
      console.warn("Recognition start:", e);
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

  // --- Settings Modal ---
  if (btnSettings) {
    btnSettings.addEventListener("click", () => {
      if (apiKeyInput) apiKeyInput.value = apiKey;
      populateVoiceList();
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

      if (voiceSelect && voiceSelect.value) {
        selectedVoiceUri = voiceSelect.value;
        localStorage.setItem("pah_voice_uri", selectedVoiceUri);
      }

      if (settingsModal) settingsModal.classList.remove("active");
      appendAssistantMessage("Paramètres et voix enregistrés avec succès !");
    });
  }

  // --- Navigation Tabs ---
  navItems.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetView = btn.getAttribute("data-view");
      navItems.forEach((n) => n.classList.remove("active"));
      btn.classList.add("active");

      Object.keys(views).forEach((k) => {
        if (views[k]) views[k].classList.toggle("active", k === targetView);
      });

      if (targetView === "shopping") {
        fetchShoppingList();
      } else if (targetView === "meals") {
        if (currentMealSubview === "today") {
          fetchMealToday();
        } else {
          fetchMealWeek();
        }
      }
    });
  });

  // --- Suggestion Chips & Form Input ---
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

  document.querySelectorAll(".chip-btn").forEach((chip) => {
    chip.addEventListener("click", () => {
      const text = chip.getAttribute("data-query") || chip.textContent.trim();
      sendInteraction(text);
    });
  });

  // --- Universal Interaction Call ---
  async function sendInteraction(text) {
    appendUserMessage(text);
    const headers = { "Content-Type": "application/json" };
    if (apiKey) headers["X-API-Key"] = apiKey;

    try {
      const res = await fetch("/api/v1/interact", {
        method: "POST",
        headers: headers,
        body: JSON.stringify({ query: text })
      });

      if (res.status === 401) {
        appendAssistantMessage("Erreur 401 : Clé API manquante ou invalide. Cliquez sur l'engrenage pour la renseigner.");
        return;
      }

      if (!res.ok) {
        appendAssistantMessage(`Erreur serveur (${res.status}).`);
        return;
      }

      const data = await res.json();
      appendAssistantMessage(data.spoken_response);
      speak(data.spoken_response);
    } catch (err) {
      appendAssistantMessage("Impossible de joindre le serveur. Vérifiez la connexion.");
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
          <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z"/>
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

  // ==========================================
  // SHOPPING LIST VIEW (Cette semaine / Liste d'attente)
  // ==========================================
  if (tabCetteSemaine && tabListeAttente) {
    tabCetteSemaine.addEventListener("click", () => {
      currentShoppingSubview = "cette-semaine";
      tabCetteSemaine.classList.add("active");
      tabListeAttente.classList.remove("active");
      if (btnClearBought) btnClearBought.style.display = "none";
      renderShoppingItems();
    });

    tabListeAttente.addEventListener("click", () => {
      currentShoppingSubview = "liste-attente";
      tabListeAttente.classList.add("active");
      tabCetteSemaine.classList.remove("active");
      if (btnClearBought) btnClearBought.style.display = "block";
      renderShoppingItems();
    });
  }

  async function fetchShoppingList() {
    if (!shoppingListContainer) return;
    shoppingListContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted)">Chargement des courses...</div>';

    const headers = { "Content-Type": "application/json" };
    if (apiKey) headers["X-API-Key"] = apiKey;

    try {
      const res = await fetch("/api/v1/interact", {
        method: "POST",
        headers: headers,
        body: JSON.stringify({ query: "Donne-moi la liste de courses" })
      });

      if (!res.ok) {
        shoppingListContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--accent-rose)">Impossible de charger les courses.</div>';
        return;
      }

      const payload = await res.json();
      const pData = payload.data || {};
      const shopObj = pData.shopping_list || {};

      cachedShoppingData.waiting_list = pData.waiting_list || shopObj.waiting_list || [];
      cachedShoppingData.current_week_items = pData.current_week_items || shopObj.current_week_items || [];

      if (badgeCetteSemaine) badgeCetteSemaine.textContent = cachedShoppingData.current_week_items.length;
      if (badgeListeAttente) badgeListeAttente.textContent = cachedShoppingData.waiting_list.length;

      renderShoppingItems();
    } catch (err) {
      shoppingListContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--accent-rose)">Erreur de connexion lors du chargement.</div>';
    }
  }

  function renderShoppingItems() {
    if (!shoppingListContainer) return;

    const isWaiting = currentShoppingSubview === "liste-attente";
    const rawItems = isWaiting ? cachedShoppingData.waiting_list : cachedShoppingData.current_week_items;

    if (!rawItems || rawItems.length === 0) {
      shoppingListContainer.innerHTML = `
        <div style="text-align:center; padding:40px 20px; color:var(--text-muted)">
          <p>Aucun article dans ${isWaiting ? "la liste d'attente" : "la liste de cette semaine"}.</p>
        </div>`;
      return;
    }

    // Group by Rayon
    const grouped = {};
    rawItems.forEach((it) => {
      const name = isWaiting ? it.item : it.name;
      const isBought = isWaiting ? it.is_bought : it.checked;
      const rayon = it.rayon || "Divers";
      if (!grouped[rayon]) grouped[rayon] = [];
      grouped[rayon].push({ name, isBought, raw: it });
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
        const checkedClass = item.isBought ? "checked" : "";
        html += `
          <div class="shopping-item-row ${checkedClass}" data-item="${encodeURIComponent(item.name)}" data-is-waiting="${isWaiting}">
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

    // Toggle Checkbox event listener
    shoppingListContainer.querySelectorAll(".shopping-item-row").forEach((row) => {
      row.addEventListener("click", async () => {
        const itemName = decodeURIComponent(row.getAttribute("data-item"));
        const fromWaiting = row.getAttribute("data-is-waiting") === "true";
        const wasChecked = row.classList.contains("checked");

        row.classList.toggle("checked");

        // If from Liste_Attente, call API to persist bought status on Google Sheet
        if (fromWaiting && !wasChecked) {
          const headers = { "Content-Type": "application/json" };
          if (apiKey) headers["X-API-Key"] = apiKey;
          try {
            await fetch("/api/v1/interact", {
              method: "POST",
              headers: headers,
              body: JSON.stringify({ query: `J'ai acheté ${itemName}` })
            });
          } catch (e) {
            console.warn("Failed to mark bought:", e);
          }
        }
      });
    });
  }

  // Clear Bought Items
  if (btnClearBought) {
    btnClearBought.addEventListener("click", async () => {
      if (!confirm("Voulez-vous vider les articles cochés de la liste d'attente ?")) return;
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
        fetchShoppingList();
      } catch (err) {
        alert("Erreur lors du nettoyage de la liste");
      }
    });
  }

  // ==========================================
  // MEALS VIEW (Aujourd'hui / Toute la semaine)
  // ==========================================
  if (tabMealToday && tabMealWeek) {
    tabMealToday.addEventListener("click", () => {
      currentMealSubview = "today";
      tabMealToday.classList.add("active");
      tabMealWeek.classList.remove("active");
      fetchMealToday();
    });

    tabMealWeek.addEventListener("click", () => {
      currentMealSubview = "week";
      tabMealWeek.classList.add("active");
      tabMealToday.classList.remove("active");
      fetchMealWeek();
    });
  }

  async function fetchMealToday() {
    if (!mealContainer) return;
    mealContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted)">Chargement du repas du jour...</div>';

    const headers = { "Content-Type": "application/json" };
    if (apiKey) headers["X-API-Key"] = apiKey;

    try {
      const res = await fetch("/api/v1/interact", {
        method: "POST",
        headers: headers,
        body: JSON.stringify({ query: "Qu'est-ce qu'on mange aujourd'hui ?" })
      });

      if (!res.ok) {
        mealContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--accent-rose)">Impossible de charger le repas.</div>';
        return;
      }

      const payload = await res.json();
      const pData = payload.data || {};
      const plan = pData.plan || pData.meal_plan || {};
      const dateStr = plan.date_str || "Aujourd'hui";
      const dayName = plan.day_name || "Ce jour";
      const lunch = plan.lunch || "Rien de planifié";
      const dinner = plan.dinner || "Rien de planifié";
      const lunchIng = pData.lunch_ingredients || [];
      const dinnerIng = pData.dinner_ingredients || [];

      function renderIngChips(list) {
        if (!list || list.length === 0) return "";
        return `
          <div class="ingredients-section">
            <div class="ingredients-title">🥕 Ingrédients nécessaires :</div>
            <div class="tags-list">
              ${list.map((ing) => `<span class="tag-chip">${ing}</span>`).join("")}
            </div>
          </div>
        `;
      }

      mealContainer.innerHTML = `
        <div class="meal-hero-card">
          <span class="meal-date-badge">${dayName} • ${dateStr}</span>
          <div class="meal-block">
            <div class="meal-time-label">Midi (Déjeuner)</div>
            <div class="meal-dish-name">${lunch}</div>
            ${renderIngChips(lunchIng)}
          </div>
          <div class="meal-block" style="margin-top:20px;">
            <div class="meal-time-label">Soir (Dîner)</div>
            <div class="meal-dish-name">${dinner}</div>
            ${renderIngChips(dinnerIng)}
          </div>
        </div>

        <div style="margin-top:20px;">
          <h3 class="section-title" style="margin-bottom:12px; font-size:1rem;">Questions rapides</h3>
          <div style="display:flex; flex-direction:column; gap:8px;">
            <button class="chip-btn" style="text-align:left; padding:10px 14px;" data-query="Qu'est-ce qu'on mange demain soir ?">
              🌙 Qu'est-ce qu'on mange demain soir ?
            </button>
            <button class="chip-btn" style="text-align:left; padding:10px 14px;" data-query="Quels sont les ingrédients pour la quiche lorraine ?">
              📖 Ingrédients pour la quiche lorraine
            </button>
          </div>
        </div>
      `;

      mealContainer.querySelectorAll(".chip-btn").forEach((chip) => {
        chip.addEventListener("click", () => {
          const q = chip.getAttribute("data-query");
          document.querySelector('.nav-item[data-view="chat"]').click();
          sendInteraction(q);
        });
      });
    } catch (err) {
      mealContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--accent-rose)">Erreur de connexion.</div>';
    }
  }

  async function fetchMealWeek() {
    if (!mealContainer) return;
    mealContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted)">Chargement du planning de la semaine...</div>';

    const headers = { "Content-Type": "application/json" };
    if (apiKey) headers["X-API-Key"] = apiKey;

    try {
      const res = await fetch("/api/v1/meals/week", { headers });
      if (!res.ok) {
        mealContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--accent-rose)">Impossible de charger le planning de la semaine.</div>';
        return;
      }

      const data = await res.json();
      const weekPlan = data.week_plan || [];

      if (weekPlan.length === 0) {
        mealContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted)">Aucun repas trouvé pour cette semaine.</div>';
        return;
      }

      function renderIngChips(list) {
        if (!list || list.length === 0) return "";
        return `
          <div class="ingredients-section" style="margin-top:4px;">
            <div class="tags-list">
              ${list.map((ing) => `<span class="tag-chip" style="font-size:0.72rem; padding:2px 6px;">${ing}</span>`).join("")}
            </div>
          </div>
        `;
      }

      let html = '<div class="week-cards-list">';
      weekPlan.forEach((day) => {
        const todayClass = day.is_today ? "today" : "";
        const todayBadge = day.is_today ? '<span class="today-tag">AUJOURD\'HUI</span>' : "";

        html += `
          <div class="week-day-card ${todayClass}">
            <div class="week-day-header">
              <span class="week-day-title">${day.day_label}</span>
              ${todayBadge}
            </div>

            <div class="week-meal-item">
              <span class="week-meal-type">Midi :</span>
              <span class="week-meal-dish">${day.lunch || "—"}</span>
              ${renderIngChips(day.lunch_ingredients)}
            </div>

            <div class="week-meal-item" style="margin-top:8px;">
              <span class="week-meal-type">Soir :</span>
              <span class="week-meal-dish">${day.dinner || "—"}</span>
              ${renderIngChips(day.dinner_ingredients)}
            </div>
          </div>
        `;
      });
      html += '</div>';

      mealContainer.innerHTML = html;
    } catch (err) {
      mealContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--accent-rose)">Erreur de connexion.</div>';
    }
  }

  // Handling URL action param (shortcuts)
  const urlParams = new URLSearchParams(window.location.search);
  const actionParam = urlParams.get("action");
  if (actionParam === "shopping_list") {
    document.querySelector('.nav-item[data-view="shopping"]').click();
  } else if (actionParam === "meal_today") {
    document.querySelector('.nav-item[data-view="meals"]').click();
  }
});
