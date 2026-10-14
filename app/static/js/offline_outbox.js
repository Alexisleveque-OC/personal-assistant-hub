// Module de File d'Attente Hors-Ligne & Synchronisation PWA (Offline Outbox)
import { postInteract, postInteractAudio } from "./api.js";
import { getActiveSessionId } from "./config.js";
import { showToastSuccess, showToastInfo, showToastError } from "./toast.js";

const DB_NAME = "pah_offline_db";
const DB_VERSION = 1;
const STORE_NAME = "outbox";
const FALLBACK_KEY = "pah_offline_outbox_fallback";

let isSyncing = false;
let syncSuccessCallback = null;
let autoRetryTimer = null;

// ============================================================================
// 1. Gestion de la persistance locale (IndexedDB avec fallback LocalStorage)
// ============================================================================

function openDatabase() {
  return new Promise((resolve) => {
    if (typeof window === "undefined" || !window.indexedDB) {
      resolve(null);
      return;
    }
    const req = window.indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: "id" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => {
      console.warn("[Outbox] Erreur ouverture IndexedDB, bascule fallback LocalStorage:", req.error);
      resolve(null);
    };
  });
}

export async function saveToOutbox(item) {
  const db = await openDatabase();
  if (db) {
    try {
      await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, "readwrite");
        const store = tx.objectStore(STORE_NAME);
        const req = store.put(item);
        req.onsuccess = () => resolve(true);
        req.onerror = () => reject(req.error);
      });
      return true;
    } catch (err) {
      console.warn("[Outbox] Échec d'écriture IndexedDB, repli LocalStorage:", err);
      return saveToFallback(item);
    }
  }
  return saveToFallback(item);
}

export async function getPendingRequests() {
  let idbItems = [];
  const db = await openDatabase();
  if (db) {
    idbItems = await new Promise((resolve) => {
      try {
        const tx = db.transaction(STORE_NAME, "readonly");
        const store = tx.objectStore(STORE_NAME);
        const req = store.getAll();
        req.onsuccess = () => resolve(req.result || []);
        req.onerror = () => resolve([]);
      } catch (e) {
        resolve([]);
      }
    });
  }

  const fallbackItems = getFallbackItems();
  // Fusionner et dédupliquer par ID
  const map = new Map();
  for (const it of [...idbItems, ...fallbackItems]) {
    map.set(it.id, it);
  }
  const items = Array.from(map.values());
  items.sort((a, b) => (a.createdAt > b.createdAt ? 1 : -1));
  return items;
}

export async function deleteFromOutbox(id) {
  deleteFromFallback(id);
  const db = await openDatabase();
  if (db) {
    try {
      await new Promise((resolve) => {
        const tx = db.transaction(STORE_NAME, "readwrite");
        const store = tx.objectStore(STORE_NAME);
        const req = store.delete(id);
        req.onsuccess = () => resolve(true);
        req.onerror = () => resolve(true);
      });
    } catch (e) {
      // ignore
    }
  }
  return true;
}

// Fallback LocalStorage si IndexedDB indisponible
function saveToFallback(item) {
  try {
    const list = getFallbackItems();
    // Cloner sans référence directe Blob qui casserait JSON.stringify
    const safeItem = { ...item };
    delete safeItem.audioBlob;
    list.push(safeItem);
    localStorage.setItem(FALLBACK_KEY, JSON.stringify(list));
    return true;
  } catch (e) {
    console.warn("[Outbox] Fallback LocalStorage plein ou bloqué:", e);
    return false;
  }
}

function getFallbackItems() {
  try {
    return JSON.parse(localStorage.getItem(FALLBACK_KEY) || "[]");
  } catch (e) {
    return [];
  }
}

function deleteFromFallback(id) {
  try {
    const list = getFallbackItems().filter((i) => i.id !== id);
    localStorage.setItem(FALLBACK_KEY, JSON.stringify(list));
    return true;
  } catch (e) {
    return false;
  }
}

// Helpers de conversion Blob <-> Base64
function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

function base64ToBlob(base64Data, defaultMime = "audio/webm") {
  try {
    const parts = base64Data.split(",");
    const mimeMatch = parts[0].match(/:(.*?);/);
    const mime = mimeMatch ? mimeMatch[1] : defaultMime;
    const bstr = atob(parts[1] || parts[0]);
    let n = bstr.length;
    const u8arr = new Uint8Array(n);
    while (n--) {
      u8arr[n] = bstr.charCodeAt(n);
    }
    return new Blob([u8arr], { type: mime });
  } catch (err) {
    console.error("[Outbox] Erreur reconstruction Blob:", err);
    return null;
  }
}

// ============================================================================
// 2. Fonctions publiques d'enfilement (Enqueue)
// ============================================================================

export async function enqueueTextRequest(queryText, sessionId = null) {
  const item = {
    id: "txt_" + Date.now() + "_" + Math.random().toString(36).substr(2, 5),
    type: "text",
    query: queryText,
    sessionId: sessionId || getActiveSessionId(),
    createdAt: new Date().toISOString(),
    status: "pending",
  };
  await saveToOutbox(item);
  await updateOutboxIndicator();
  startAutoRetry();
  console.info(`[Outbox] Requête texte mise en attente hors-ligne : "${queryText}"`);
  return item;
}

export async function enqueueAudioRequest(audioBlob, sessionId = null) {
  let base64 = null;
  try {
    base64 = await blobToBase64(audioBlob);
  } catch (e) {
    console.warn("[Outbox] Encodage base64 pour fallback échoué:", e);
  }

  const item = {
    id: "aud_" + Date.now() + "_" + Math.random().toString(36).substr(2, 5),
    type: "audio",
    audioBlob: audioBlob, // Stockage direct du Blob natif pour IndexedDB
    audioBase64: base64,  // Fallback LocalStorage si besoin
    mimeType: audioBlob.type || "audio/webm",
    sessionId: sessionId || getActiveSessionId(),
    createdAt: new Date().toISOString(),
    status: "pending",
  };
  await saveToOutbox(item);
  await updateOutboxIndicator();
  startAutoRetry();
  console.info(`[Outbox] Requête audio (${Math.round(audioBlob.size / 1024)} Ko) mise en attente hors-ligne`);
  return item;
}

export async function getPendingOutboxCount() {
  const items = await getPendingRequests();
  return items.length;
}

// ============================================================================
// 3. Témoin visuel Outbox dans l'interface
// ============================================================================

export async function updateOutboxIndicator() {
  const indicator = document.getElementById("offline-outbox-indicator");
  if (!indicator) return;

  const count = await getPendingOutboxCount();
  if (count > 0) {
    indicator.style.display = "inline-flex";
    indicator.classList.add("visible");
    indicator.innerHTML = `
      <span class="outbox-icon">⏳</span>
      <span class="outbox-label">${count} en attente</span>
    `;
    indicator.title = `${count} commande(s) hors-ligne en attente de synchronisation. Cliquez pour synchroniser maintenant.`;
  } else {
    indicator.style.display = "none";
    indicator.classList.remove("visible");
  }
}

// ============================================================================
// 4. Synchronisation automatique dès reconnexion (Sync Outbox) & Auto-Retry
// ============================================================================

export function setSyncSuccessHandler(callback) {
  syncSuccessCallback = callback;
}

export function startAutoRetry() {
  if (autoRetryTimer) return;
  autoRetryTimer = setInterval(async () => {
    const count = await getPendingOutboxCount();
    if (count === 0) {
      stopAutoRetry();
      return;
    }
    // Tenter de synchroniser si non en cours
    if (!isSyncing) {
      syncOutbox(true);
    }
  }, 4000);
}

export function stopAutoRetry() {
  if (autoRetryTimer) {
    clearInterval(autoRetryTimer);
    autoRetryTimer = null;
  }
}

export async function syncOutbox(force = false) {
  if (isSyncing) return;
  // Ne pas tenter si le navigateur est explicitement hors-ligne et qu'on ne force pas
  if (!force && typeof navigator !== "undefined" && !navigator.onLine) {
    return;
  }

  const items = await getPendingRequests();
  if (items.length === 0) {
    stopAutoRetry();
    await updateOutboxIndicator();
    return;
  }

  isSyncing = true;
  console.info(`[Outbox] Tentative de synchronisation de ${items.length} requête(s) en attente...`);

  let syncedCount = 0;

  for (const item of items) {
    try {
      let res = null;
      if (item.type === "text") {
        res = await postInteract(item.query, item.sessionId);
      } else if (item.type === "audio") {
        let blob = item.audioBlob instanceof Blob ? item.audioBlob : null;
        if (!blob && item.audioBase64) {
          blob = base64ToBlob(item.audioBase64, item.mimeType);
        }
        if (blob) {
          res = await postInteractAudio(blob, item.sessionId);
        } else {
          console.warn("[Outbox] Blob audio corrompu ou manquant, suppression de l'item:", item.id);
          await deleteFromOutbox(item.id);
          continue;
        }
      }

      if (res && res.ok && res.status === 200) {
        const data = await res.json();
        // Vérification de sécurité contre les réponses 503/fallback de Service Worker
        if (data.spoken_response && data.spoken_response.includes("hors connexion")) {
          console.warn("[Outbox] Réponse simulée hors connexion reçue, arrêt du rejeu pour cet essai");
          break;
        }

        await deleteFromOutbox(item.id);
        syncedCount++;

        if (syncSuccessCallback) {
          try {
            syncSuccessCallback(item, data);
          } catch (cbErr) {
            console.error("[Outbox] Erreur dans syncSuccessCallback:", cbErr);
          }
        }
      } else {
        console.warn(`[Outbox] Échec requête (${res?.status}), report de la synchronisation.`);
        break;
      }
    } catch (err) {
      console.warn("[Outbox] Erreur réseau lors du rejeu outbox:", err);
      break;
    }
  }

  isSyncing = false;
  await updateOutboxIndicator();

  const remaining = await getPendingOutboxCount();
  if (remaining === 0) {
    stopAutoRetry();
  }

  if (syncedCount > 0) {
    showToastSuccess(
      `${syncedCount} commande(s) synchronisée(s) avec succès !`,
      "Synchronisation Otis ✅"
    );
  }
}

// Initialisation globale des écouteurs de connectivité
export function initOfflineSync(onSuccessHandler = null) {
  if (onSuccessHandler) {
    setSyncSuccessHandler(onSuccessHandler);
  }

  if (typeof window !== "undefined") {
    // 1. Déclencheur événement online standard
    window.addEventListener("online", () => {
      console.info("[Outbox] Événement 'online' reçu : tentative de synchronisation immédiate");
      syncOutbox(true);
    });

    // 2. Déclencheur événement offline
    window.addEventListener("offline", () => {
      console.info("[Outbox] Événement 'offline' reçu : passage en mode hors-ligne");
      updateOutboxIndicator();
    });

    // 3. Déclencheur retour sur l'application / déverrouillage écran en running
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        syncOutbox(true);
      }
    });

    // 4. Déclencheur focus fenêtre
    window.addEventListener("focus", () => {
      syncOutbox(true);
    });
  }

  // Vérification initiale au démarrage
  updateOutboxIndicator().then(() => {
    getPendingOutboxCount().then((count) => {
      if (count > 0) {
        startAutoRetry();
        syncOutbox(true);
      }
    });
  });
}
