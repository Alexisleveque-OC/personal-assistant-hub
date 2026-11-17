// Interrupteur « Mains-libres » du menu : active / coupe la détection du mot-clé « Otis » et le confirme par un toast.
import { setWakeWordEnabled, updateWakeWordIndicator } from "./wake_word.js";
import { showToastInfo, showToastSuccess } from "./toast.js";

export function initHandsFreeSwitch() {
  // Refonte UX : l'indicateur est dans l'interrupteur « Mains-libres » du menu (un <label>) ; c'est la case qui bascule,
  // un écouteur de clic sur l'indicateur basculerait une seconde fois.
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

  // Initialisation du statut visuel du Wake-Word
  updateWakeWordIndicator();
}
