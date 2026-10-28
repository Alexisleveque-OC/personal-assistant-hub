// Gestionnaire Audio Focus & Ducking Casque (Running Mode & PWA)
// Permet de mixer la musique/podcasts en arrière-plan et de n'atténuer le son (ducking)
// que pendant les interventions vocales précises (Otis parle ou l'utilisateur parle).

// Clip porteur : sur Chrome Android, speechSynthesis ne demande pas le focus audio (musique jamais baissée)
// et navigator.audioSession n'existe pas. Une balise <audio> courte et quasi silencieuse jouée pendant la
// réponse fait baisser la musique ; la vider (et non la mettre en pause) rend le focus (diagnostic du 28/10).
const CARRIER_SECONDS = 1;

/**
 * WAV 8 kHz mono 16 bits, bruit vers -70 dBFS : inaudible sous la musique mais pas un silence numérique.
 */
export function buildNearSilentWav(seconds) {
  const sampleRate = 8000;
  const sampleCount = seconds * sampleRate;
  const view = new DataView(new ArrayBuffer(44 + sampleCount * 2));
  const writeText = (offset, text) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };
  writeText(0, "RIFF");
  view.setUint32(4, 36 + sampleCount * 2, true);
  writeText(8, "WAVE");
  writeText(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeText(36, "data");
  view.setUint32(40, sampleCount * 2, true);
  for (let i = 0; i < sampleCount; i++) view.setInt16(44 + i * 2, Math.round((Math.random() * 2 - 1) * 10), true);
  return new Blob([view.buffer], { type: "audio/wav" });
}

export class AudioFocusManager {
  constructor() {
    this.activeReasons = new Set();
    this.currentSessionMode = "ambient";
    this.audioSessionSupported = typeof navigator !== "undefined" && "audioSession" in navigator;
    this.hasCarrierElement = false;
    this.carrierAudio = null;
    this.carrierUrl = null;

    // Gestion de la visibilité pour libérer l'audio en arrière-plan
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
          // En arrière-plan, libération préventive de toute atténuation résiduelle
          this.releaseAllDucking();
        }
      });
    }
  }

  /**
   * Initialise la session audio du navigateur en mode 'ambient' (non-intrusif)
   * pour ne jamais couper ni baisser la musique au démarrage de l'app.
   */
  initAudioSession() {
    this.setAudioSessionMode("ambient");
  }

  /**
   * Configure le mode de la session audio W3C / WebKit si disponible.
   * - 'ambient' : mixe avec les autres applications sans ducking ni pause (mode repos nominal)
   * - 'transient' : signale au système une intervention courte pour déclencher le ducking temporaire (TTS)
   * - 'play-and-record' : capture et restitution vocale (dictée / micro)
   */
  setAudioSessionMode(mode) {
    this.currentSessionMode = mode;
    if (this.audioSessionSupported && navigator.audioSession) {
      try {
        navigator.audioSession.type = mode;
      } catch (err) {
        console.debug("[AudioFocus] navigator.audioSession.type non supporté:", err);
      }
    }
  }

  /**
   * Vérifie si le ducking (atténuation du volume externe) est actuellement actif.
   */
  isDucking() {
    return this.activeReasons.size > 0;
  }

  /**
   * Déclenche l'atténuation du son pour un motif spécifique ('tts' ou 'recording').
   */
  requestDucking(reason = "tts") {
    const wasDucking = this.isDucking();
    this.activeReasons.add(reason);

    if (reason === "recording") {
      this.setAudioSessionMode("play-and-record");
    } else {
      this.setAudioSessionMode("transient");
      this.startCarrier();
    }

    if (!wasDucking) {
      this.dispatchDuckingEvent(true, reason);
    }
  }

  /**
   * Restaure le volume nominal lorsque l'interaction vocale se termine.
   */
  releaseDucking(reason = "tts") {
    this.activeReasons.delete(reason);
    if (reason !== "recording") {
      this.stopCarrier();
    }

    if (this.activeReasons.size === 0) {
      this.setAudioSessionMode("ambient");
      this.dispatchDuckingEvent(false, reason);
    } else if (!this.activeReasons.has("recording")) {
      // S'il ne reste que du TTS
      this.setAudioSessionMode("transient");
    }
  }

  /**
   * Libère immédiatement tous les verrous d'atténuation.
   */
  releaseAllDucking() {
    if (this.activeReasons.size > 0) {
      this.activeReasons.clear();
      this.stopCarrier();
      this.setAudioSessionMode("ambient");
      this.dispatchDuckingEvent(false, "all");
    }
  }

  /**
   * Joue le clip porteur en boucle (une seule balise, réutilisée d'une réponse à l'autre).
   */
  startCarrier() {
    if (!this.carrierAudio) {
      this.carrierUrl = URL.createObjectURL(buildNearSilentWav(CARRIER_SECONDS));
      this.carrierAudio = new Audio();
      this.carrierAudio.loop = true;
      this.hasCarrierElement = true;
    }
    if (this.carrierAudio.getAttribute("src")) return;
    this.carrierAudio.src = this.carrierUrl;
    this.carrierAudio.play().catch((err) => {
      console.warn("[AudioFocus] Clip porteur refusé, la musique ne sera pas baissée:", `${err.name}: ${err.message}`);
    });
  }

  /**
   * Vide la balise du clip porteur : une simple pause garderait le focus audio (musique jamais remontée).
   */
  stopCarrier() {
    if (!this.carrierAudio || !this.carrierAudio.getAttribute("src")) return;
    this.carrierAudio.pause();
    this.carrierAudio.removeAttribute("src");
    this.carrierAudio.load();
  }

  /**
   * Émet des événements globaux pour synchroniser l'UI ou des composants tiers.
   */
  dispatchDuckingEvent(isDucking, reason) {
    if (typeof window !== "undefined") {
      const eventName = isDucking ? "pah-audio-ducking-start" : "pah-audio-ducking-end";
      window.dispatchEvent(
        new CustomEvent(eventName, {
          detail: {
            reason,
            isDucking,
            activeReasons: Array.from(this.activeReasons),
            sessionMode: this.currentSessionMode,
          },
        })
      );
    }
  }
}

// Instance singleton
export const audioFocusManager = new AudioFocusManager();
