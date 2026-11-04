// Journal du micro (diagnostic sur téléphone, sans câble ni console) : les événements du mot-clé, de la dictée
// et de l'envoi sont gardés dans localStorage, partagé entre la PWA installée et Chrome, et relus par
// /static/audio_diag.html. Un journal en panne prévient dans la console mais ne bloque jamais le micro.

export const VOICE_DIAG_STORAGE_KEY = "pah_voice_diag_log";
export const VOICE_DIAG_MAX_ENTRIES = 300;

function defaultStorage() {
  try {
    return globalThis.localStorage || null;
  } catch (err) {
    return null;
  }
}

export function createVoiceDiagLog({
  storage = defaultStorage(),
  now = () => new Date(),
  max = VOICE_DIAG_MAX_ENTRIES,
  consoleSink = console,
} = {}) {
  // Sans stockage (navigation privée, Node) : journal en mémoire pour la session en cours.
  let memoryEntries = [];

  function read() {
    if (!storage) return memoryEntries.slice();
    const raw = storage.getItem(VOICE_DIAG_STORAGE_KEY);
    if (!raw) return [];
    try {
      const entries = JSON.parse(raw);
      if (Array.isArray(entries)) return entries;
      throw new TypeError("le contenu n'est pas une liste");
    } catch (err) {
      consoleSink.warn(`[Journal micro] ${VOICE_DIAG_STORAGE_KEY} illisible, journal réinitialisé : ${err.message}`);
      return [];
    }
  }

  function write(entries) {
    if (!storage) {
      memoryEntries = entries;
      return;
    }
    try {
      storage.setItem(VOICE_DIAG_STORAGE_KEY, JSON.stringify(entries));
    } catch (err) {
      consoleSink.warn(`[Journal micro] Écriture impossible dans ${VOICE_DIAG_STORAGE_KEY} : ${err.message}`);
    }
  }

  function record(source, message) {
    consoleSink.debug(`[${source}] ${message}`);
    const entries = read();
    entries.push({ at: now().toISOString(), source, message });
    write(entries.slice(-max));
  }

  function clear() {
    write([]);
  }

  return { record, read, clear };
}

export function formatVoiceDiagEntries(entries) {
  return entries.map((entry) => `${entry.at} [${entry.source}] ${entry.message}`).join("\n");
}

export const voiceDiagLog = createVoiceDiagLog();
