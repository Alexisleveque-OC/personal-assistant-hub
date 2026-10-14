// Gestionnaire Audio Focus & Ducking Casque (Running Mode & PWA)
// Permet de mixer la musique/podcasts en arrière-plan et de n'atténuer le son (ducking)
// que pendant les interventions vocales précises (Otis parle ou l'utilisateur parle).

export class AudioFocusManager {
  constructor() {
    this.activeReasons = new Set();
    this.currentSessionMode = "ambient";
    this.audioSessionSupported = typeof navigator !== "undefined" && "audioSession" in navigator;
    this.hasCarrierElement = false;
    this.carrierAudio = null;

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
      this.setAudioSessionMode("ambient");
      this.dispatchDuckingEvent(false, "all");
    }
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
