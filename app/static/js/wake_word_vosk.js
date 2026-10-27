// Détection locale du mot-clé « Otis » via Vosk (WASM) :
// micro brut (sans traitements audio) pour ne jamais prendre le focus audio et laisser la musique intacte,
// reconnaissance restreinte au seul mot-clé, échecs explicites (WakeWordLoadError) plutôt que silencieux.

const VOSK_BASE = "/static/vendor/vosk";
const VOSK_CLIENT_URL = "/static/vendor/vosk/vosk.wasm.js";
const VOSK_WORKER_URL = "/static/vendor/vosk/vosk.worker.js";
const VOSK_WASM_URL = "/static/vendor/vosk/vosk.wasm";
// L'URL du modèle sert de clé au cache IndexedDB du worker : la version force un nouveau téléchargement au changement.
// Route dédiée en flux (app/routers/wake_word.py) : Cloud Run refuse les fichiers statiques > 32 Mio.
const VOSK_MODEL_URL = "/vosk/model.tar.gz?v=vosk-browser-0.0.3+vosk-model-small-fr-0.22";
const CAPTURE_WORKLET_URL = "/static/js/vosk_capture_worklet.js";

const WAKE_WORD = "otis";
const WAKE_GRAMMAR = JSON.stringify(["otis", "[unk]"]);
const LOAD_TIMEOUT_MS = 120000;
const RAW_MIC_CONSTRAINTS = {
  audio: {
    echoCancellation: false,
    noiseSuppression: false,
    autoGainControl: false,
    channelCount: 1,
  },
};

export class WakeWordLoadError extends Error {
  constructor(message, cause = null) {
    super(message);
    this.name = "WakeWordLoadError";
    this.cause = cause;
  }
}

// « Otis » doit être le dernier mot avant la pause : en grammaire restreinte, un mot proche suivi d'autres
// mots (« les hôtes sont arrivés » → « otis [unk] ») serait sinon pris pour le mot-clé.
export function transcriptHasWakeWord(text) {
  if (!text) return false;
  const words = text.toLowerCase().trim().split(/\s+/);
  return words[words.length - 1] === WAKE_WORD;
}

// Chargement unique du modèle (≈ 40 Mo au premier usage, puis lu depuis IndexedDB) partagé par tous les détecteurs.
let voskClientPromise = null;

function loadVoskClient(log) {
  if (voskClientPromise) return voskClientPromise;

  voskClientPromise = (async () => {
    let module;
    try {
      module = await import(VOSK_CLIENT_URL);
    } catch (err) {
      throw new WakeWordLoadError(`Moteur Vosk introuvable (${VOSK_CLIENT_URL}) : ${err.message}`, err);
    }

    const startedAt = performance.now();
    const client = new module.VoskClient({
      modelUrl: VOSK_MODEL_URL,
      workerUrl: VOSK_WORKER_URL,
      wasmUrl: VOSK_WASM_URL,
      logLevel: -1,
    });

    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(new WakeWordLoadError(`Chargement du modèle Vosk trop long (> ${LOAD_TIMEOUT_MS / 1000} s, ${VOSK_MODEL_URL})`));
      }, LOAD_TIMEOUT_MS);
      client.on("load", (message) => {
        clearTimeout(timer);
        if (message.result) resolve();
        else reject(new WakeWordLoadError(`Le modèle Vosk n'a pas pu être chargé (${VOSK_MODEL_URL})`));
      });
      client.on("error", (message) => {
        clearTimeout(timer);
        reject(new WakeWordLoadError(`Erreur du moteur Vosk : ${message.error}`));
      });
    });

    log(`Modèle Vosk prêt en ${((performance.now() - startedAt) / 1000).toFixed(1)} s`);
    return client;
  })();

  // Un échec ne doit pas rester mémorisé : une nouvelle tentative recharge le moteur.
  voskClientPromise.catch(() => {
    voskClientPromise = null;
  });
  return voskClientPromise;
}

export class VoskWakeWordDetector {
  constructor({ onWake, log = () => {}, loadClient = loadVoskClient } = {}) {
    if (typeof onWake !== "function") {
      throw new TypeError("VoskWakeWordDetector : le callback onWake est obligatoire");
    }
    this.onWake = onWake;
    this.log = log;
    this.loadClient = loadClient;
    this.stream = null;
    this.audioContext = null;
    this.recognizer = null;
    this.running = false;
    // Incrémenté à chaque start()/stop() : un start() devancé par un stop() abandonne sans erreur.
    this.generation = 0;
  }

  get isRunning() {
    return this.running;
  }

  async load() {
    return this.loadClient(this.log);
  }

  async start() {
    if (this.running) return;
    const generation = ++this.generation;
    const isCancelled = () => generation !== this.generation;

    const client = await this.load();
    if (isCancelled()) return;

    let stream = null;
    let audioContext = null;
    const release = () => {
      if (stream) stream.getTracks().forEach((track) => track.stop());
      if (audioContext) audioContext.close();
    };

    try {
      stream = await navigator.mediaDevices.getUserMedia(RAW_MIC_CONSTRAINTS);
      if (isCancelled()) return release();
      audioContext = new AudioContext();
      if (audioContext.state === "suspended") await audioContext.resume();
      await audioContext.audioWorklet.addModule(CAPTURE_WORKLET_URL);
      if (isCancelled()) return release();
    } catch (err) {
      release();
      if (isCancelled()) return;
      throw new WakeWordLoadError(`Micro indisponible pour la détection locale : ${err.name || ""} ${err.message}`, err);
    }

    this.stream = stream;
    this.audioContext = audioContext;
    const sampleRate = audioContext.sampleRate;
    const recognizer = new client.KaldiRecognizer(sampleRate, WAKE_GRAMMAR);
    recognizer.setWords(true);
    // Résultats finaux uniquement (à la pause qui suit le mot) : les résultats partiels
    // basculent sur « otis » pour des mots proches (« les hôtes ») et provoquent de faux réveils.
    recognizer.on("result", (message) => this.handleResult(message?.result));
    recognizer.on("error", (message) => this.log(`Erreur de reconnaissance Vosk : ${message?.error}`));
    this.recognizer = recognizer;

    const source = audioContext.createMediaStreamSource(stream);
    const capture = new AudioWorkletNode(audioContext, "vosk-capture");
    capture.port.onmessage = (event) => {
      if (this.running && this.recognizer === recognizer) {
        recognizer.acceptWaveformFloat(event.data, sampleRate);
      }
    };
    source.connect(capture);

    this.running = true;
    this.log(`Écoute locale du mot-clé démarrée (${sampleRate} Hz, micro brut)`);
  }

  handleResult(result) {
    const text = result?.text;
    if (!this.running || !text || !text.includes(WAKE_WORD)) return;

    // Confiance et durée du mot « otis » journalisées pour calibrer un éventuel seuil sur la vraie voix.
    const candidate = (result.result || []).filter((word) => word.word === WAKE_WORD).pop();
    const details = candidate
      ? ` (confiance ${candidate.conf.toFixed(2)}, durée ${(candidate.end - candidate.start).toFixed(2)} s)`
      : "";

    if (!transcriptHasWakeWord(text)) {
      this.log(`Candidat ignoré : « ${text} »${details}`);
      return;
    }
    this.log(`Mot-clé détecté : « ${text} »${details}`);
    // Libère le micro avant de passer la main à la dictée.
    this.stop();
    this.onWake(text);
  }

  stop() {
    this.generation += 1;
    this.running = false;
    if (this.recognizer) {
      this.recognizer.remove();
      this.recognizer = null;
    }
    if (this.stream) {
      this.stream.getTracks().forEach((track) => track.stop());
      this.stream = null;
    }
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }
  }
}

export { VOSK_BASE, LOAD_TIMEOUT_MS };
