// Feuille Sport : import d'une capture de montre et Trophées (ancien rendu, rhabillé à l'étape 3 de la refonte).
// Les vues Semaine, Mois · Année, Séances, le détail et le formulaire Séance sont dans views/sport/ (refonte UX).
import { state } from "../config.js";
import { showToastSuccess, showToastError, showToastInfo, showToastWarning } from "../toast.js";
import { speak } from "../speech.js";
import { fetchSportGamificationData } from "../api.js";
import { importSportScreenshotWithDatePrompt, DATE_CANCELLED_CODE } from "../screenshot_import.js";

const sportGamificationContainer = document.getElementById("sport-gamification-container");

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

export async function fetchSportGamification() {
  if (!sportGamificationContainer) return;
  sportGamificationContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted)">Chargement des trophées et anecdotes...</div>';

  try {
    const data = await fetchSportGamificationData();
    renderSportGamification(data);
  } catch (err) {
    sportGamificationContainer.innerHTML = `<div style="text-align:center; padding:30px; color:var(--color-danger)">Impossible de charger les trophées (${err.message}).</div>`;
  }
}

export function renderSportGamification(data) {
  if (!sportGamificationContainer) return;
  const badges = data.badges || [];
  const prs = data.personal_records || [];
  const facts = data.fun_facts || [];
  const imminent = data.imminent_milestones || [];

  let html = `
    <div class="gamification-header-card">
      <div class="gamification-trophy-counter">
        <div class="gamification-trophy-icon">🏆</div>
        <div>
          <div class="gamification-trophy-text">${data.unlocked_count} / ${data.total_badges} Trophées</div>
          <div class="gamification-trophy-sub">Accomplissements & Paliers réguliers</div>
        </div>
      </div>
      <div style="font-size:0.85rem; font-weight:800; color:var(--color-primary);">
        ${Math.round((data.unlocked_count / (data.total_badges || 1)) * 100)}% accompli
      </div>
    </div>
  `;

  const announcements = data.announcements || [];
  if (announcements && announcements.length > 0) {
    html += `
      <div class="announcements-container">
        ${announcements.map(ann => `
          <div class="announcement-pill">
            <span>${ann}</span>
          </div>
        `).join("")}
      </div>
    `;
  }

  if (imminent && imminent.length > 0) {
    const imm = imminent[0];
    html += `
      <div class="milestone-banner">
        <div class="milestone-banner-icon">🎯</div>
        <div class="milestone-banner-content">
          <div class="milestone-banner-title">Palier Imminent</div>
          <div class="milestone-banner-text">${imm.message}</div>
        </div>
      </div>
    `;
  }

  if (prs && prs.length > 0) {
    html += `
      <div style="font-size:0.88rem; font-weight:800; color:var(--color-text); margin-bottom:8px; display:flex; align-items:center; gap:6px;">
        <span>⚡ Records Personnels (PR)</span>
      </div>
      <div class="pr-grid">
        ${prs.map(pr => `
          <div class="pr-card">
            <div class="pr-card-badge">${pr.title}</div>
            <div class="pr-card-val">${pr.formatted_value}</div>
            <div class="pr-card-sub">${pr.date ? pr.date : "-"}</div>
          </div>
        `).join("")}
      </div>
    `;
  }

  if (facts && facts.length > 0) {
    html += `
      <div style="font-size:0.88rem; font-weight:800; color:var(--color-text); margin:18px 0 8px 0; display:flex; align-items:center; gap:6px;">
        <span>💡 Équivalences Insolites & Fun</span>
      </div>
      <div class="fun-facts-container">
        ${facts.map(f => `
          <div class="fun-fact-card">
            <div class="fun-fact-icon">${f.icon}</div>
            <div class="fun-fact-body">
              <div class="fun-fact-title">${f.title}</div>
              <div class="fun-fact-text">${f.text}</div>
            </div>
          </div>
        `).join("")}
      </div>
    `;
  }

  const catLabels = {
    mono_session: "⚡ Exploits en Une Séance (Distance & Durée)",
    pop_culture: "🧙 Pop-Culture & Clins d'Œil (Otis, LOTR, Roshar)",
    distance: "🏃 Paliers de Distance Réguliers",
    denivele: "⛰️ Paliers Dénivelé (D+)",
    temps: "⏱️ Volume de Pratique & Épopée Horaires",
    regularite: "🛡️ Constance, Renfo & Éléments",
    secret: "🕵️ Badges Secrets & Easter Eggs",
    absurde: "🚀 L'Infini & l'Absurde",
  };

  const categories = [
    "mono_session",
    "pop_culture",
    "distance",
    "denivele",
    "temps",
    "regularite",
    "secret",
    "absurde",
  ];

  categories.forEach(cat => {
    const catBadges = badges.filter(b => b.category === cat);
    if (catBadges.length === 0) return;

    html += `
      <div class="badge-category-title">${catLabels[cat] || cat}</div>
      <div class="badges-grid">
        ${catBadges.map(b => {
          const isSecretLocked = b.is_secret && !b.is_unlocked;
          const itemClass = b.is_unlocked ? "unlocked" : (isSecretLocked ? "secret-locked" : "locked");
          const rarityClass = `rarity-${b.rarity || "bronze"}`;

          return `
            <div class="badge-item ${itemClass}">
              <span class="badge-rarity-pill ${rarityClass}">${b.rarity}</span>
              <div class="badge-icon-wrap">${b.icon}</div>
              <div class="badge-title">${b.title}</div>
              <div class="badge-desc">${b.description}</div>

              ${b.is_unlocked ? `
                <div class="badge-tag-unlocked">Débloqué ✅</div>
              ` : `
                ${!isSecretLocked && b.target_value ? `
                  <div class="badge-progress-wrap">
                    <div class="badge-progress-bar">
                      <div class="badge-progress-fill" style="width:${b.progress_pct}%"></div>
                    </div>
                    <div class="badge-progress-label">${b.current_value} / ${b.target_value} ${b.unit || ""} (${b.progress_pct}%)</div>
                  </div>
                ` : `
                  <div style="font-size:0.68rem; font-weight:700; color:var(--text-muted); margin-top:auto;">Mystère 🔒</div>
                `}
              `}
            </div>
          `;
        }).join("")}
      </div>
    `;
  });

  sportGamificationContainer.innerHTML = html;
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
