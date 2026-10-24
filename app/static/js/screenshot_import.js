// Import de capture sportive avec saisie manuelle de la date si Otis ne la trouve pas sur l'image
import { importSportScreenshot } from "./api.js";

export const DATE_MISSING_CODE = "screenshot_date_missing";
export const DATE_CANCELLED_CODE = "screenshot_date_cancelled";

/**
 * Importe une capture ; si l'API signale une date introuvable, demande la date puis relance l'import.
 * Lève une erreur de code DATE_CANCELLED_CODE si l'utilisateur annule la saisie.
 * @param {File} file
 * @param {{ onDatePrompt?: () => void }} options - onDatePrompt : appelé juste avant l'ouverture du sélecteur
 */
export async function importSportScreenshotWithDatePrompt(file, { onDatePrompt = null } = {}) {
  try {
    return await importSportScreenshot(file);
  } catch (err) {
    if (err.code !== DATE_MISSING_CODE) throw err;

    if (onDatePrompt) onDatePrompt();
    const chosenDate = await promptScreenshotDate(err.message);
    if (!chosenDate) {
      const cancelled = new Error("Import annulé : aucune date choisie pour la séance.");
      cancelled.code = DATE_CANCELLED_CODE;
      throw cancelled;
    }
    return await importSportScreenshot(file, { referenceDate: chosenDate });
  }
}

/** Date locale du jour au format YYYY-MM-DD (toISOString renverrait la date UTC). */
function localTodayIso() {
  const now = new Date();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${mm}-${dd}`;
}

/**
 * Ouvre une modale de choix de date (aujourd'hui par défaut, jamais dans le futur).
 * @param {string} reason - message explicatif renvoyé par l'API
 * @returns {Promise<string|null>} date YYYY-MM-DD, ou null si annulé
 */
export function promptScreenshotDate(reason) {
  return new Promise((resolve) => {
    const today = localTodayIso();

    const overlay = document.createElement("div");
    overlay.className = "modal-overlay active";
    overlay.innerHTML = `
      <div class="modal-box" style="max-width: 420px;">
        <h3 class="modal-title"><span>📅</span> Date de la séance</h3>
        <p class="screenshot-date-reason" style="font-size:0.82rem; color:var(--color-text-secondary); margin-bottom:14px;"></p>
        <div class="form-group" style="margin-bottom:16px;">
          <label class="form-label" for="screenshot-date-input">Quel jour as-tu fait cette séance ?</label>
          <input type="date" id="screenshot-date-input" class="form-input" max="${today}" value="${today}" required />
        </div>
        <div class="modal-actions" style="display:flex; justify-content:flex-end; gap:10px;">
          <button type="button" class="btn-secondary" data-action="cancel">Annuler</button>
          <button type="button" class="btn-primary" data-action="confirm">Importer à cette date</button>
        </div>
      </div>`;
    // textContent : le message API n'est jamais interprété comme du HTML
    overlay.querySelector(".screenshot-date-reason").textContent = reason || "";

    const input = overlay.querySelector("#screenshot-date-input");
    const close = (value) => {
      overlay.remove();
      resolve(value);
    };

    overlay.querySelector('[data-action="cancel"]').addEventListener("click", () => close(null));
    overlay.querySelector('[data-action="confirm"]').addEventListener("click", () => {
      const value = input.value;
      if (!value || value > today) {
        input.focus();
        return;
      }
      close(value);
    });
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close(null);
    });

    document.body.appendChild(overlay);
    input.focus();
  });
}
