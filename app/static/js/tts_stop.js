// Bouton pause : visible seulement pendant qu'Otis parle (évènement « tts-state » de tts.js), coupe la voix.
export function initTtsStop(button, onStop) {
  if (!button) {
    console.warn("[TTS] Bouton pause #btn-tts-stop introuvable : impossible de couper la voix d'Otis.");
    return;
  }
  window.addEventListener("tts-state", (event) => {
    button.hidden = !(event.detail && event.detail.speaking);
  });
  button.addEventListener("click", () => onStop());
}
