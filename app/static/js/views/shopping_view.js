// Vue Liste de Courses (Cette semaine / Liste d'attente / Rayons)
import { state, getStoredCheckedItems, setStoredCheckedItems, clearStoredCheckedItems } from "../config.js";
import { speak } from "../speech.js";
import { postInteract, resetShoppingList, postShoppingComplete } from "../api.js";

const shoppingListContainer = document.getElementById("shopping-list-container");
const btnResetShopping = document.getElementById("btn-reset-shopping");
const btnClearBought = document.getElementById("btn-clear-bought");
const btnCheckCompletion = document.getElementById("btn-check-completion");
const completionBanner = document.getElementById("shopping-completion-banner");
const tabCetteSemaine = document.getElementById("tab-cette-semaine");
const tabListeAttente = document.getElementById("tab-liste-attente");
const badgeCetteSemaine = document.getElementById("badge-cette-semaine");
const badgeListeAttente = document.getElementById("badge-liste-attente");

export async function fetchShoppingList() {
  if (!shoppingListContainer) return;
  shoppingListContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted)">Chargement des courses...</div>';

  try {
    const res = await postInteract("Donne-moi la liste de courses");

    if (!res.ok) {
      shoppingListContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--accent-rose)">Impossible de charger les courses.</div>';
      return;
    }

    const payload = await res.json();
    const pData = payload.data || {};
    const shopObj = pData.shopping_list || {};

    state.cachedShoppingData.waiting_list = pData.waiting_list || shopObj.waiting_list || [];
    state.cachedShoppingData.current_week_items = pData.current_week_items || shopObj.current_week_items || [];
    state.cachedShoppingData.rayons_order = pData.rayons_order || shopObj.rayons_order || null;

    if (badgeCetteSemaine) badgeCetteSemaine.textContent = state.cachedShoppingData.current_week_items.length;
    if (badgeListeAttente) badgeListeAttente.textContent = state.cachedShoppingData.waiting_list.length;

    renderShoppingItems();
  } catch (err) {
    shoppingListContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--accent-rose)">Erreur de connexion lors du chargement.</div>';
  }
}

export function renderShoppingItems() {
  if (!shoppingListContainer) return;

  const isWaiting = state.currentShoppingSubview === "liste-attente";
  const rawItems = isWaiting ? state.cachedShoppingData.waiting_list : state.cachedShoppingData.current_week_items;

  if (!rawItems || rawItems.length === 0) {
    shoppingListContainer.innerHTML = `
      <div style="text-align:center; padding:40px 20px; color:var(--text-muted)">
        <p>Aucun article dans ${isWaiting ? "la liste d'attente" : "la liste de cette semaine"}.</p>
      </div>`;
    return;
  }

  const storedChecked = getStoredCheckedItems();

  // Groupement par Rayon
  const grouped = {};
  rawItems.forEach((it) => {
    const name = isWaiting ? it.item : it.name;
    const isBought = isWaiting ? it.is_bought : (it.checked || storedChecked.includes(name));
    const rayon = it.rayon || "Divers";
    if (!grouped[rayon]) grouped[rayon] = [];
    grouped[rayon].push({ name, isBought, raw: it });
  });

  function normRayon(r) {
    return (r || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim();
  }

  const defaultRayonsOrder = {
    "fruits": 1,
    "legumes": 2,
    "plat prepare": 3,
    "viande": 4,
    "charcuterie": 5,
    "dessert": 6,
    "fromage/beurre/creme": 7,
    "apero": 8,
    "oeufs/farine/lait": 9,
    "petit dej + bio": 10,
    "produit du monde": 11,
    "epicerie": 12,
    "boisson": 13,
    "hygiene": 14,
    "pq + entretien": 15,
    "surgele": 16,
    "divers": 999
  };

  const rawOrder = state.cachedShoppingData.rayons_order || {};
  const normalizedOrderMap = { ...defaultRayonsOrder };
  Object.keys(rawOrder).forEach((k) => {
    normalizedOrderMap[normRayon(k)] = rawOrder[k];
  });

  const sortedRayonNames = Object.keys(grouped).sort((a, b) => {
    const nA = normRayon(a);
    const nB = normRayon(b);
    const ordA = normalizedOrderMap[nA] !== undefined ? normalizedOrderMap[nA] : 900;
    const ordB = normalizedOrderMap[nB] !== undefined ? normalizedOrderMap[nB] : 900;
    if (ordA !== ordB) return ordA - ordB;
    return a.localeCompare(b);
  });

  let html = "";
  sortedRayonNames.forEach((rayon) => {
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

  // Bouton de fin des courses
  html += `
    <button id="btn-finish-shopping-bottom" class="btn-finish-big">
      🏁 J'ai fini mes courses !
    </button>
  `;

  shoppingListContainer.innerHTML = html;

  // Clic sur une ligne d'article
  shoppingListContainer.querySelectorAll(".shopping-item-row").forEach((row) => {
    row.addEventListener("click", async () => {
      const itemName = decodeURIComponent(row.getAttribute("data-item"));
      const fromWaiting = row.getAttribute("data-is-waiting") === "true";
      const wasChecked = row.classList.contains("checked");

      row.classList.toggle("checked");
      const isNowChecked = !wasChecked;

      if (!fromWaiting) {
        let stored = getStoredCheckedItems();
        if (isNowChecked) {
          if (!stored.includes(itemName)) stored.push(itemName);
        } else {
          stored = stored.filter((it) => it !== itemName);
        }
        setStoredCheckedItems(stored);

        const target = state.cachedShoppingData.current_week_items.find((it) => it.name === itemName);
        if (target) target.checked = isNowChecked;
      } else {
        const target = state.cachedShoppingData.waiting_list.find((it) => it.item === itemName);
        if (target) target.is_bought = isNowChecked;
      }
    });
  });

  const btnBottomFinish = document.getElementById("btn-finish-shopping-bottom");
  if (btnBottomFinish) {
    btnBottomFinish.addEventListener("click", checkShoppingCompletion);
  }
}

export async function checkShoppingCompletion() {
  const storedChecked = getStoredCheckedItems();
  const isWaiting = state.currentShoppingSubview === "liste-attente";

  // Articles cochés dans Cette semaine et Liste d'attente
  const checkedCurrent = (state.cachedShoppingData.current_week_items || [])
    .filter((it) => it.checked || storedChecked.includes(it.name))
    .map((it) => it.name);

  const checkedWaiting = (state.cachedShoppingData.waiting_list || [])
    .filter((it) => it.is_bought)
    .map((it) => it.item);

  // Synchronisation groupée vers Google Sheets (Cette semaine + Liste d'attente)
  let syncSuccess = false;
  if (checkedCurrent.length > 0 || checkedWaiting.length > 0) {
    try {
      await postShoppingComplete({
        current_week_items: checkedCurrent,
        waiting_items: checkedWaiting,
      });
      syncSuccess = true;
      clearStoredCheckedItems();
      (state.cachedShoppingData.current_week_items || []).forEach((it) => {
        if (checkedCurrent.includes(it.name)) it.checked = true;
      });
    } catch (err) {
      console.warn("Échec de synchronisation Google Sheets:", err);
    }
  }

  let remaining = [];
  if (isWaiting) {
    remaining = (state.cachedShoppingData.waiting_list || [])
      .filter((it) => !it.is_bought)
      .map((it) => it.item);
  } else {
    remaining = (state.cachedShoppingData.current_week_items || [])
      .filter((it) => !it.checked && !storedChecked.includes(it.name))
      .map((it) => it.name);
  }

  if (completionBanner) {
    const syncBadge = syncSuccess ? "<div style='margin-top:6px; font-size:0.85rem; color:#4ade80; font-weight:600;'>✅ Synchronisé dans votre Google Sheet (Cette semaine & Liste d'attente)</div>" : "";
    if (remaining.length === 0) {
      completionBanner.className = "completion-banner success";
      completionBanner.innerHTML = `
        <div>
          <span>🎉 <strong>Félicitations !</strong> Vous avez tout pris dans votre liste. Vos courses sont complètes !</span>
          ${syncBadge}
        </div>
      `;
      completionBanner.style.display = "block";
      speak("Félicitations, vous avez tout pris ! Vos courses sont complètes et enregistrées dans le Google Sheet.");
    } else {
      completionBanner.className = "completion-banner warning";
      completionBanner.innerHTML = `
        <div>
          <span>⚠️ <strong>Attention, il vous reste encore ${remaining.length} article(s) à prendre :</strong></span>
          <div style="margin-top:6px; font-size:0.85rem; display:flex; flex-wrap:wrap; gap:4px;">
            ${remaining.map((it) => `<span style="background:rgba(0,0,0,0.25); padding:2px 7px; border-radius:4px; font-weight:600;">${it}</span>`).join("")}
          </div>
          ${syncBadge}
        </div>
      `;
      completionBanner.style.display = "block";
      speak(`Attention, il vous reste encore ${remaining.length} article(s) à prendre : ${remaining.slice(0, 4).join(", ")}.`);
    }
    completionBanner.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

export function initShoppingView() {
  if (tabCetteSemaine && tabListeAttente) {
    tabCetteSemaine.addEventListener("click", () => {
      state.currentShoppingSubview = "cette-semaine";
      tabCetteSemaine.classList.add("active");
      tabListeAttente.classList.remove("active");
      if (btnClearBought) btnClearBought.style.display = "none";
      if (btnResetShopping) btnResetShopping.style.display = "inline-block";
      renderShoppingItems();
    });

    tabListeAttente.addEventListener("click", () => {
      state.currentShoppingSubview = "liste-attente";
      tabListeAttente.classList.add("active");
      tabCetteSemaine.classList.remove("active");
      if (btnClearBought) btnClearBought.style.display = "block";
      if (btnResetShopping) btnResetShopping.style.display = "none";
      renderShoppingItems();
    });
  }

  if (btnCheckCompletion) {
    btnCheckCompletion.addEventListener("click", checkShoppingCompletion);
  }

  if (btnResetShopping) {
    btnResetShopping.addEventListener("click", async () => {
      if (!confirm("Voulez-vous réinitialiser tous les articles cochés pour cette semaine ?")) return;
      try {
        clearStoredCheckedItems();
        if (state.cachedShoppingData.current_week_items) {
          state.cachedShoppingData.current_week_items.forEach((it) => {
            it.checked = false;
          });
        }
        if (completionBanner) completionBanner.style.display = "none";
        renderShoppingItems();
        await resetShoppingList();
        speak("La liste de courses de la semaine a été réinitialisée.");
        await fetchShoppingList();
      } catch (err) {
        alert("Erreur lors de la réinitialisation : " + err.message);
      }
    });
  }

  if (btnClearBought) {
    btnClearBought.addEventListener("click", async () => {
      if (!confirm("Voulez-vous vider les articles cochés de la liste d'attente ?")) return;
      try {
        const res = await postInteract("Vide la liste de courses");
        const data = await res.json();
        alert(data.spoken_response || "Articles nettoyés");
        fetchShoppingList();
      } catch (err) {
        alert("Erreur lors du nettoyage de la liste");
      }
    });
  }
}
