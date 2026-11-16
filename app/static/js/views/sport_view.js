// Feuille Sport : import d'une capture de montre.
// Les vues Semaine, Mois · Année, Séances, le détail, le formulaire Séance et les Trophées sont dans views/sport/ (refonte UX).
import { state } from "../config.js";
import { showToastSuccess, showToastError, showToastInfo, showToastWarning } from "../toast.js";
import { speak } from "../speech.js";
import { importSportScreenshotWithDatePrompt, DATE_CANCELLED_CODE } from "../screenshot_import.js";

// Capture de montre (Strava, Decathlon, CW500) : Otis extrait la séance et l'enregistre ; la feuille se rafraîchit.
export async function handleSportScreenshotUpload(file) {
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    showToastWarning("Le fichier sélectionné n'est pas une image valide.", "Format non supporté");
    return;
  }

  const toastAnalyzing = showToastInfo("Analyse de la capture par Otis en cours...", "Analyse Otis", { duration: 0 });

  try {
    const data = await importSportScreenshotWithDatePrompt(file, {
      onDatePrompt: () => toastAnalyzing.dismiss(),
    });
    toastAnalyzing.dismiss();

    const spokenMsg = data.spoken_response || "Votre séance de sport a été importée avec succès !";
    showToastSuccess(spokenMsg, "Séance enregistrée ✅");
    if (state.ttsEnabled) speak(spokenMsg);
    window.dispatchEvent(new CustomEvent("sport-data-updated"));
  } catch (err) {
    toastAnalyzing.dismiss();
    if (err.code === DATE_CANCELLED_CODE) {
      showToastInfo(err.message, "Import annulé");
      return;
    }
    console.error("Erreur import screenshot sport:", err);
    showToastError(err.message || "Impossible d'extraire les données de la course.", "Échec de l'import");
  }
}

// Bouton « capture de montre » de la barre d'actions et collage (Ctrl+V) d'une image sur la feuille Sport.
export function initSportView() {
  const btnImportScreenshot = document.getElementById("btn-import-sport-screenshot");
  const fileScreenshotInput = document.getElementById("file-sport-screenshot-input");
  if (btnImportScreenshot && fileScreenshotInput) {
    btnImportScreenshot.addEventListener("click", () => fileScreenshotInput.click());
    fileScreenshotInput.addEventListener("change", (e) => {
      const file = e.target.files && e.target.files[0];
      if (file) {
        handleSportScreenshotUpload(file);
        fileScreenshotInput.value = "";
      }
    });
  }

  window.addEventListener("paste", (e) => {
    const activeView = document.getElementById("view-sport");
    if (!activeView || !activeView.classList.contains("active")) return;

    const items = (e.clipboardData || e.originalEvent.clipboardData)?.items;
    if (!items) return;

    for (let i = 0; i < items.length; i++) {
      if (items[i].type.indexOf("image") !== -1) {
        const file = items[i].getAsFile();
        if (file) {
          e.preventDefault();
          handleSportScreenshotUpload(file);
          break;
        }
      }
    }
  });
}
