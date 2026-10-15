// Vue Sport Running, Mini-Coach Otis, Dashboard & Gamification
import { state } from "../config.js";
import {
  showToast,
  showToastSuccess,
  showToastError,
  showToastInfo,
  showToastWarning,
} from "../toast.js";
import { speak } from "../speech.js";
import {
  fetchSportTodayData,
  fetchSportDashboardData,
  fetchSportGamificationData,
  fetchSportSessionsData,
  fetchSportSummariesData,
  patchSportSession,
  patchSportSessionById,
  deleteSportSession,
  createSportSession,
  importSportScreenshot,
} from "../api.js";

export async function handleSportScreenshotUpload(file) {
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    showToastWarning("Le fichier sélectionné n'est pas une image valide.", "Format non supporté");
    return;
  }

  const statusBox = document.getElementById("sport-import-status");
  if (statusBox) {
    statusBox.style.display = "block";
    statusBox.style.background = "rgba(37, 99, 235, 0.1)";
    statusBox.style.color = "var(--color-primary)";
    statusBox.style.border = "1px solid rgba(37, 99, 235, 0.2)";
    statusBox.innerHTML = "⏳ <strong>Analyse en cours par Otis...</strong> Extraction de la distance, durée, allure et métriques.";
  }

  const toastAnalyzing = showToastInfo("Analyse de la capture par Otis en cours...", "Analyse Otis", { duration: 0 });

  try {
    const data = await importSportScreenshot(file);
    toastAnalyzing.dismiss();

    const spokenMsg = data.spoken_response || "Votre séance de sport a été importée avec succès !";
    showToastSuccess(spokenMsg, "Séance enregistrée ✅");

    if (statusBox) {
      statusBox.style.display = "block";
      statusBox.style.background = "rgba(34, 197, 94, 0.12)";
      statusBox.style.color = "#16a34a";
      statusBox.style.border = "1px solid rgba(34, 197, 94, 0.3)";
      statusBox.innerHTML = `✅ <strong>Séance enregistrée !</strong><br>${escapeHtml(spokenMsg)}`;
    }

    // Synthèse vocale si activée
    if (state.ttsEnabled && typeof speak === "function") {
      speak(spokenMsg);
    }

    // Rafraîchir les données et l'interface
    if (typeof fetchSportToday === "function") fetchSportToday();
    if (typeof fetchSportSessions === "function") fetchSportSessions();
    if (typeof fetchSportSummaries === "function") fetchSportSummaries();
    if (typeof fetchSportDashboard === "function") fetchSportDashboard();
    window.dispatchEvent(new CustomEvent("sport-data-updated"));
  } catch (err) {
    toastAnalyzing.dismiss();
    console.error("Erreur import screenshot sport:", err);
    if (statusBox) {
      statusBox.style.display = "block";
      statusBox.style.background = "rgba(239, 68, 68, 0.1)";
      statusBox.style.color = "#dc2626";
      statusBox.style.border = "1px solid rgba(239, 68, 68, 0.3)";
      statusBox.innerHTML = `❌ <strong>Erreur lors de l'import :</strong> ${escapeHtml(err.message || "Impossible d'extraire les données.")}`;
    }
    showToastError(err.message || "Impossible d'extraire les données de la course.", "Échec de l'import");
  }
}

function escapeHtml(str) {
  return String(str || "").replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[m]);
}

const sportTodayContainer = document.getElementById("sport-today-container");
const sportSessionsContainer = document.getElementById("sport-sessions-container");
const sportSummariesContainer = document.getElementById("sport-summaries-container");
const sportImportContainer = document.getElementById("sport-import-container");
const sportDashboardContainer = document.getElementById("sport-dashboard-container");
const sportGamificationContainer = document.getElementById("sport-gamification-container");
const sportCoachBubble = document.getElementById("sport-coach-bubble");

const tabSportToday = document.getElementById("tab-sport-today");
const tabSportSessions = document.getElementById("tab-sport-sessions");
const tabSportSummaries = document.getElementById("tab-sport-summaries");
const tabSportImport = document.getElementById("tab-sport-import");
const tabSportDash = document.getElementById("tab-sport-dash");
const tabSportGamification = document.getElementById("tab-sport-gamification");
const sportTodayBadgeDate = document.getElementById("sport-today-badge-date");

export function switchSportSubview(subview) {
  state.currentSportSubview = subview;
  if (tabSportToday) tabSportToday.classList.toggle("active", subview === "today");
  if (tabSportSessions) tabSportSessions.classList.toggle("active", subview === "sessions");
  if (tabSportSummaries) tabSportSummaries.classList.toggle("active", subview === "summaries");
  if (tabSportImport) tabSportImport.classList.toggle("active", subview === "import");
  if (tabSportDash) tabSportDash.classList.toggle("active", subview === "dashboard");
  if (tabSportGamification) tabSportGamification.classList.toggle("active", subview === "gamification");

  if (sportTodayContainer) sportTodayContainer.style.display = subview === "today" ? "block" : "none";
  if (sportSessionsContainer) sportSessionsContainer.style.display = subview === "sessions" ? "block" : "none";
  if (sportSummariesContainer) sportSummariesContainer.style.display = subview === "summaries" ? "block" : "none";
  if (sportImportContainer) sportImportContainer.style.display = subview === "import" ? "block" : "none";
  if (sportDashboardContainer) sportDashboardContainer.style.display = subview === "dashboard" ? "block" : "none";
  if (sportGamificationContainer) sportGamificationContainer.style.display = subview === "gamification" ? "block" : "none";

  if (sportCoachBubble) {
    sportCoachBubble.style.display = (subview === "today") ? "flex" : "none";
  }

  if (subview === "today") {
    fetchSportToday();
  } else if (subview === "sessions") {
    fetchSportSessions();
  } else if (subview === "summaries") {
    fetchSportSummaries();
  } else if (subview === "dashboard") {
    fetchSportDashboard(state.currentSportScale);
  } else if (subview === "gamification") {
    fetchSportGamification();
  }
}

export async function fetchSportToday() {
  if (!sportTodayContainer) return;
  sportTodayContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted)">Chargement de la séance du jour...</div>';

  try {
    const data = await fetchSportTodayData();
    renderCoachBubble(data.coach_tip);

    if (sportTodayBadgeDate && data.date) {
      const dObj = new Date(data.date + "T00:00:00");
      const options = { weekday: "short", day: "numeric", month: "short" };
      sportTodayBadgeDate.textContent = dObj.toLocaleDateString("fr-FR", options);
    }

    renderSportToday(data);
  } catch (err) {
    sportTodayContainer.innerHTML = `<div style="text-align:center; padding:30px; color:var(--color-danger)">Impossible de charger la séance du jour (${err.message}).</div>`;
  }
}

export function renderCoachBubble(coachTip) {
  if (!sportCoachBubble) return;
  if (!coachTip || !coachTip.message) {
    sportCoachBubble.style.display = "none";
    return;
  }

  const lvl = coachTip.niveau || "info";
  sportCoachBubble.className = `coach-bubble ${lvl}`;
  const avatarIcon = lvl === "alerte" ? "⚠️" : (lvl === "vigilance" ? "💡" : "🏃");
  const titleLabel = lvl === "alerte" ? "Alerte Sécurité Coach Otis" : (lvl === "vigilance" ? "Conseil Vigilance Coach" : "Le Mot du Coach Otis");

  sportCoachBubble.innerHTML = `
    <div class="coach-avatar">${avatarIcon}</div>
    <div class="coach-bubble-body">
      <div class="coach-bubble-title">${titleLabel}</div>
      <div class="coach-bubble-message">${coachTip.message}</div>
    </div>
  `;
  sportCoachBubble.style.display = "flex";
}

export function renderSportToday(data) {
  const seances = data.seances || [];
  const comparisons = data.comparisons || [];

  let spotlightHtml = "";
  if (data.daily_spotlight) {
    spotlightHtml = `
      <div class="daily-spotlight-card">
        <div class="daily-spotlight-icon">🎙️</div>
        <div class="daily-spotlight-content">
          <div class="daily-spotlight-title">Le Mot d'Otis · Annonce du Jour</div>
          <div class="daily-spotlight-text">${data.daily_spotlight}</div>
        </div>
      </div>
    `;
  }

  if (seances.length === 0) {
    sportTodayContainer.innerHTML = `
      ${spotlightHtml}
      <div class="sport-session-card" style="text-align:center; padding:28px 16px;">
        <div style="font-size:2.2rem; margin-bottom:8px;">🛋️</div>
        <h3 style="font-size:1.15rem; font-weight:800; color:var(--color-text); margin-bottom:6px;">Journée de repos</h3>
        <p style="font-size:0.88rem; color:var(--color-text-secondary); line-height:1.5; margin-bottom:14px;">
          Aucune séance planifiée ou enregistrée aujourd'hui. Laisse ton corps et tes tibias se régénérer !
        </p>
        <button type="button" class="btn-import-today-trigger btn-secondary" style="width:100%; display:inline-flex; align-items:center; justify-content:center; gap:8px; font-weight:700;">
          📸 Importer une course courue aujourd'hui
        </button>
      </div>
    `;
    const btn = sportTodayContainer.querySelector(".btn-import-today-trigger");
    if (btn) btn.addEventListener("click", () => switchSportSubview("import"));
    return;
  }

  let html = spotlightHtml;

  seances.forEach((s, idx) => {
    const isRealise = s.statut === "Réalisé";
    const statusClass = isRealise ? "realise" : (s.statut === "Repos" ? "repos" : "prevu");
    const statusLabel = s.statut || "Prévu";

    const typeEmoji = s.type_seance === "Renforcement" ? "🏋️" : (s.type_seance === "Fractionné" ? "⚡" : (s.type_seance === "Sortie Longue" ? "🏔️" : "🏃"));
    const titleLabel = `${typeEmoji} ${s.type_seance || "Course"}`;

    const comp = comparisons.find(c => c.current_session.type_seance === s.type_seance);

    html += `
      <div class="sport-session-card" data-session-idx="${idx}" data-session-date="${s.date}" data-session-type="${s.type_seance}">
        <div class="sport-card-header">
          <div class="sport-card-title">${titleLabel}</div>
          <span class="badge-status ${statusClass}">${statusLabel}</span>
        </div>

        <div class="sport-metrics-grid">
          ${s.distance_km ? `
            <div class="sport-metric-box">
              <div class="sport-metric-label">Distance</div>
              <div class="sport-metric-val">${s.distance_km}<span class="sport-metric-unit"> km</span></div>
            </div>
          ` : ""}

          ${s.allure_formatted || s.allure_cible ? `
            <div class="sport-metric-box">
              <div class="sport-metric-label">${isRealise ? "Allure" : "Allure Cible"}</div>
              <div class="sport-metric-val">${s.allure_formatted || s.allure_cible}</div>
            </div>
          ` : ""}

          ${s.km_effort ? `
            <div class="sport-metric-box">
              <div class="sport-metric-label">Km-Effort</div>
              <div class="sport-metric-val">${s.km_effort}</div>
            </div>
          ` : ""}

          ${s.ressenti_rpe ? `
            <div class="sport-metric-box">
              <div class="sport-metric-label">RPE</div>
              <div class="sport-metric-val" style="color:${getRpeColor(s.ressenti_rpe)}">${s.ressenti_rpe}<span class="sport-metric-unit">/10</span></div>
            </div>
          ` : ""}

          ${s.charge_rpe ? `
            <div class="sport-metric-box">
              <div class="sport-metric-label">Charge RPE</div>
              <div class="sport-metric-val" style="font-weight:700; color:var(--color-accent);">${s.charge_rpe}</div>
            </div>
          ` : ""}

          ${s.meteo_note ? `
            <div class="sport-metric-box">
              <div class="sport-metric-label">Météo</div>
              <div class="sport-metric-val">${getMeteoBadge(s.meteo_note)}</div>
            </div>
          ` : ""}

          ${s.fc_moyenne ? `
            <div class="sport-metric-box">
              <div class="sport-metric-label">FC Moy</div>
              <div class="sport-metric-val">${s.fc_moyenne}<span class="sport-metric-unit"> bpm</span></div>
            </div>
          ` : ""}
        </div>

        ${s.programme ? `
          <div class="sport-details-block">
            <div class="sport-details-label">Programme</div>
            <div>${s.programme}</div>
          </div>
        ` : ""}

        ${s.remarques ? `
          <div class="sport-details-block" style="border-left-color:var(--color-accent)">
            <div class="sport-details-label">Remarques & Sensations</div>
            <div>${s.remarques}</div>
          </div>
        ` : ""}

        ${comp && comp.deltas && comp.deltas.length > 0 ? `
          <div class="sport-comparison-box">
            <div class="sport-comparison-title">
              📊 vs Dernière séance (${comp.previous_session.date})
            </div>
            <div class="comparison-badges">
              ${comp.deltas.map(d => {
                const arrow = d.trend === "up" ? "↑" : (d.trend === "down" ? "↓" : "=");
                const trendClass = d.trend === "up" ? "trend-up" : (d.trend === "down" ? "trend-down" : "trend-stable");
                const metricLabel = d.metric === "vitesse_kmh" ? "Vitesse" : (d.metric === "distance_km" ? "Distance" : "Km-Effort");
                const sign = d.delta_pct > 0 ? "+" : "";
                return `<span class="comp-badge ${trendClass}">${arrow} ${metricLabel} ${sign}${d.delta_pct}%</span>`;
              }).join("")}
            </div>
          </div>
        ` : ""}

        <div class="sport-feedback-section">
          <div class="sport-feedback-title">
            <span>Ressenti d'effort & Notes</span>
            <span id="rpe-feedback-label-${idx}" style="font-size:0.78rem; font-weight:700; color:var(--text-muted);">
              ${s.ressenti_rpe ? `Note actuelle : ${s.ressenti_rpe}/10` : "Non renseigné"}
            </span>
          </div>

          <div class="rpe-scale-container" data-idx="${idx}">
            ${[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(val => `
              <button type="button" class="rpe-pill-btn ${s.ressenti_rpe === val ? "selected" : ""}" data-rpe="${val}">
                ${val}
              </button>
            `).join("")}
          </div>

          <textarea class="sport-notes-textarea" id="sport-notes-${idx}" placeholder="Notes de sensations, douleurs tibias, météo..." rows="2"></textarea>

          <button type="button" class="sport-btn-save" id="btn-save-sport-${idx}">
            💾 Enregistrer mon ressenti
          </button>

          <div class="session-actions-bar" style="display:flex; justify-content:flex-end; gap:8px; margin-top:14px; padding-top:10px; border-top:1px solid rgba(255,255,255,0.08);">
            <button type="button" class="btn-today-edit-session btn-secondary" data-session-idx="${idx}" style="display:inline-flex; align-items:center; gap:6px; font-size:0.8rem; padding:5px 10px; border-radius:6px; cursor:pointer;">
              ✏️ Modifier tout
            </button>
            <button type="button" class="btn-today-delete-session" data-session-idx="${idx}" style="display:inline-flex; align-items:center; gap:6px; font-size:0.8rem; padding:5px 10px; border-radius:6px; color:#ef4444; background:rgba(239, 68, 68, 0.1); border:1px solid rgba(239, 68, 68, 0.2); cursor:pointer;">
              🗑️ Supprimer
            </button>
          </div>
        </div>
      </div>
    `;
  });

  html += `
    <div style="margin-top:14px; text-align:center;">
      <button type="button" class="btn-import-today-trigger btn-secondary" style="width:100%; font-size:0.86rem; padding:10px 14px; display:inline-flex; align-items:center; justify-content:center; gap:8px; font-weight:700;">
        📸 Importer une séance par capture d'écran
      </button>
    </div>
  `;

  sportTodayContainer.innerHTML = html;

  const importTrigger = sportTodayContainer.querySelector(".btn-import-today-trigger");
  if (importTrigger) {
    importTrigger.addEventListener("click", () => switchSportSubview("import"));
  }

  seances.forEach((s, idx) => {
    attachSportFeedbackHandlers(idx, s);
  });
}

export function getRpeColor(rpe) {
  if (rpe <= 4) return "#2e7d32";
  if (rpe <= 7) return "#f57c00";
  return "#d32f2f";
}

export function getMeteoBadge(note) {
  if (!note && note !== 0) return "-";
  const n = Number(note);
  let icon = "🌤️";
  if (n <= 2) icon = "☀️";
  else if (n <= 4) icon = "🌤️";
  else if (n <= 6) icon = "🌦️";
  else if (n <= 8) icon = "🌧️";
  else icon = "⛈️";
  return `${icon} ${n}/10`;
}

export function attachSportFeedbackHandlers(idx, session) {
  const card = document.querySelector(`.sport-session-card[data-session-idx="${idx}"]`);
  if (!card) return;

  let selectedRpe = session.ressenti_rpe || null;
  const rpeButtons = card.querySelectorAll(".rpe-pill-btn");
  const feedbackLabel = document.getElementById(`rpe-feedback-label-${idx}`);
  const notesInput = document.getElementById(`sport-notes-${idx}`);
  const saveBtn = document.getElementById(`btn-save-sport-${idx}`);

  rpeButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const val = parseInt(btn.getAttribute("data-rpe"), 10);
      selectedRpe = val;
      rpeButtons.forEach(b => b.classList.remove("selected"));
      btn.classList.add("selected");
      if (feedbackLabel) {
        const desc = val <= 4 ? "Facile" : (val <= 7 ? "Soutenu" : "Très dur / Limite");
        feedbackLabel.textContent = `Sélectionné : ${val}/10 (${desc})`;
        feedbackLabel.style.color = getRpeColor(val);
      }
    });
  });

  if (saveBtn) {
    saveBtn.addEventListener("click", async () => {
      const textVal = notesInput ? notesInput.value.trim() : "";
      if (!selectedRpe && !textVal) {
        showToastWarning("Veuillez choisir une note RPE ou saisir une remarque.", "Ressenti manquant");
        return;
      }

      saveBtn.disabled = true;
      saveBtn.textContent = "⏳ Enregistrement...";

      const payload = { target_type: session.type_seance };
      if (selectedRpe) payload.ressenti_rpe = selectedRpe;
      if (textVal) {
        payload.remarques = textVal;
        payload.append_remarques = true;
      }

      try {
        await patchSportSession(session.date, payload);
        saveBtn.textContent = "✅ Enregistré avec succès !";
        saveBtn.style.background = "var(--color-success)";
        showToastSuccess("Débrief de séance enregistré avec succès !", "Ressenti sauvegardé");
        setTimeout(() => {
          fetchSportToday();
        }, 900);
      } catch (err) {
        console.error("Erreur de sauvegarde de debrief sport:", err);
        saveBtn.disabled = false;
        saveBtn.textContent = "❌ Échec. Réessayer";
        saveBtn.title = err.message || "Erreur de communication";
        saveBtn.style.background = "var(--color-danger)";
        showToastError(err.message || "Erreur de communication avec le serveur.", "Échec d'enregistrement");
      }
    });
  }

  const todayEditBtn = card.querySelector(".btn-today-edit-session");
  const todayDelBtn = card.querySelector(".btn-today-delete-session");
  if (todayEditBtn) {
    todayEditBtn.addEventListener("click", () => openEditSessionModal(session));
  }
  if (todayDelBtn) {
    todayDelBtn.addEventListener("click", async () => {
      const sessionId = session.id;
      if (!sessionId) {
        showToastError("ID de séance introuvable.", "Erreur");
        return;
      }
      if (!confirm(`Supprimer la séance du jour (${session.type_seance || "Course"}) ?\n\nCette action est irréversible et recalculera automatiquement vos bilans.`)) return;
      todayDelBtn.disabled = true;
      todayDelBtn.textContent = "⏳ Suppression...";
      try {
        await deleteSportSession(sessionId);
        showToastSuccess("Séance supprimée et bilans hebdomadaires recalculés.", "Séance supprimée");
        await fetchSportToday();
        if (typeof fetchSportSummaries === "function") fetchSportSummaries();
        if (typeof fetchSportDashboard === "function") fetchSportDashboard();
        window.dispatchEvent(new CustomEvent("sport-data-updated"));
      } catch (err) {
        showToastError("Erreur de suppression : " + err.message, "Erreur");
        todayDelBtn.disabled = false;
        todayDelBtn.textContent = "🗑️ Supprimer";
      }
    });
  }
}

export async function fetchSportDashboard(scale = "week") {
  if (!sportDashboardContainer) return;
  sportDashboardContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted)">Chargement du tableau de bord...</div>';

  try {
    const data = await fetchSportDashboardData(scale);
    renderSportDashboard(data);
  } catch (err) {
    sportDashboardContainer.innerHTML = `<div style="text-align:center; padding:30px; color:var(--color-danger)">Impossible de charger le tableau de bord (${err.message}).</div>`;
  }
}

export function renderSportDashboard(data) {
  const totals = data.totals || {};
  const series = data.series || [];

  let html = `
    <div class="dash-scale-switcher">
      <button class="dash-scale-btn ${data.scale === "week" ? "active" : ""}" data-scale="week">Semaine</button>
      <button class="dash-scale-btn ${data.scale === "month" ? "active" : ""}" data-scale="month">Mois</button>
      <button class="dash-scale-btn ${data.scale === "year" ? "active" : ""}" data-scale="year">Année</button>
    </div>

    <div style="font-size:0.95rem; font-weight:800; color:var(--color-text); margin-bottom:12px;">
      ${data.label}
    </div>

    <div class="dash-kpi-grid">
      <div class="dash-kpi-card">
        <div class="dash-kpi-title">Volume Total</div>
        <div class="dash-kpi-val">${totals.km_effort || 0} <span style="font-size:0.8rem; font-weight:600;">km-effort</span></div>
        <div class="dash-kpi-sub">${totals.distance_km || 0} km · ${totals.nb_seances || 0} séances (${totals.nb_renfo || 0} renfo)</div>
      </div>

      <div class="dash-kpi-card">
        <div class="dash-kpi-title">Allure Moyenne</div>
        <div class="dash-kpi-val">${totals.allure_formatted || "-"}</div>
        <div class="dash-kpi-sub">${totals.vitesse_kmh ? totals.vitesse_kmh + " km/h" : "Hors renfo"}</div>
      </div>

      <div class="dash-kpi-card">
        <div class="dash-kpi-title">Charge RPE</div>
        <div class="dash-kpi-val">${totals.charge_rpe || 0}</div>
        <div class="dash-kpi-sub">Charge interne cumulée</div>
      </div>

      <div class="dash-kpi-card">
        <div class="dash-kpi-title">Sécurité & Plafond</div>
        <div class="dash-kpi-val" style="font-size:1.05rem;">${data.plafond_km_effort ? data.plafond_km_effort + " km-eff max" : "Normal"}</div>
        <div class="dash-kpi-sub">${data.alerte_securite || "Progression suivie"}</div>
      </div>
    </div>

    <div class="dash-chart-card">
      <div class="dash-chart-header">
        <div class="dash-chart-title">Évolution Volume (Km-Effort)</div>
      </div>
      <div class="svg-chart-wrapper">
        ${renderSvgBarChart(series, data.plafond_km_effort)}
      </div>
    </div>
  `;

  sportDashboardContainer.innerHTML = html;

  sportDashboardContainer.querySelectorAll(".dash-scale-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const sc = btn.getAttribute("data-scale");
      state.currentSportScale = sc;
      fetchSportDashboard(sc);
    });
  });
}

export function renderSvgBarChart(series, plafond) {
  if (!series || series.length === 0) {
    return '<div style="text-align:center; padding:20px; color:var(--text-muted)">Aucune donnée de série</div>';
  }

  const maxVal = Math.max(...series.map(s => s.km_effort || 0), plafond || 0, 10);
  const chartHeight = 130;
  const barWidth = 24;
  const gap = 12;
  const totalWidth = series.length * (barWidth + gap) + 20;

  let svg = `<svg viewBox="0 0 ${totalWidth} ${chartHeight + 28}" style="width:100%; min-width:${totalWidth}px; height:${chartHeight + 28}px;">`;

  if (plafond && maxVal > 0) {
    const yPlafond = chartHeight - (plafond / maxVal) * (chartHeight - 20);
    svg += `
      <line x1="0" y1="${yPlafond}" x2="${totalWidth}" y2="${yPlafond}" stroke="#d32f2f" stroke-dasharray="4 4" stroke-width="1.5" opacity="0.75" />
      <text x="6" y="${yPlafond - 4}" fill="#d32f2f" font-size="9" font-weight="700">Plafond +10% (${plafond} km-eff)</text>
    `;
  }

  series.forEach((pt, i) => {
    const x = 10 + i * (barWidth + gap);
    const val = pt.km_effort || 0;
    const barH = maxVal > 0 ? (val / maxVal) * (chartHeight - 24) : 0;
    const y = chartHeight - barH;
    const fill = pt.is_current ? "var(--color-primary)" : "var(--color-accent-soft)";
    const stroke = pt.is_current ? "var(--color-primary-hover)" : "var(--color-accent)";

    svg += `
      <rect x="${x}" y="${y}" width="${barWidth}" height="${barH}" rx="4" fill="${fill}" stroke="${stroke}" stroke-width="1" />
      <text x="${x + barWidth / 2}" y="${y - 4}" text-anchor="middle" font-size="9" font-weight="700" fill="var(--color-text)">${val > 0 ? val : ""}</text>
      <text x="${x + barWidth / 2}" y="${chartHeight + 16}" text-anchor="middle" font-size="10" font-weight="${pt.is_current ? "800" : "500"}" fill="${pt.is_current ? "var(--color-primary)" : "var(--color-text-secondary)"}">${pt.label}</text>
    `;
  });

  svg += '</svg>';
  return svg;
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

// ==========================================================================
// HISTORIQUE CHRONOLOGIQUE DES SÉANCES (Étape 3)
// ==========================================================================

export function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return null;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) {
    return `${h}h${m < 10 ? "0" + m : m}min`;
  }
  return `${m} min${s > 0 ? " " + s + "s" : ""}`;
}

export function formatDateFr(dateStr) {
  if (!dateStr) return "";
  try {
    const d = new Date(dateStr + "T00:00:00");
    return d.toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
  } catch (e) {
    return dateStr;
  }
}

export function getTypeClass(typeSeance) {
  if (!typeSeance) return "type-ef";
  const clean = typeSeance.toLowerCase();
  if (clean.includes("vitesse")) return "type-vitesse";
  if (clean.includes("fractionn")) return "type-fractionne";
  if (clean.includes("longue")) return "type-sortie-longue";
  if (clean.includes("course")) return "type-course";
  if (clean.includes("renfo") || clean.includes("musculation") || clean.includes("ppg")) return "type-renforcement";
  if (clean.includes("recup") || clean.includes("récup")) return "type-recup";
  if (clean.includes("tempo")) return "type-tempo";
  return "type-ef";
}

export function getTypeEmoji(typeSeance) {
  if (!typeSeance) return "🏃";
  const clean = typeSeance.toLowerCase();
  if (clean.includes("vitesse")) return "🚀";
  if (clean.includes("course")) return "👟";
  if (clean.includes("renfo") || clean.includes("musculation") || clean.includes("ppg")) return "🏋️";
  if (clean.includes("fractionn")) return "⚡";
  if (clean.includes("longue")) return "🏔️";
  if (clean.includes("tempo")) return "🔥";
  if (clean.includes("recup") || clean.includes("récup")) return "🌱";
  return "🏃";
}

export function hasPainAlert(text) {
  if (!text) return false;
  const lower = text.toLowerCase();
  return (
    lower.includes("périostite") ||
    lower.includes("periostite") ||
    lower.includes("douleur") ||
    lower.includes("mal") ||
    lower.includes("tibia") ||
    lower.includes("mollet") ||
    lower.includes("gêne") ||
    lower.includes("gene") ||
    lower.includes("tension")
  );
}

let cachedSessionsList = [];
let currentFilterType = "all";
let currentFilterStatus = "all";

export async function fetchSportSessions() {
  if (!sportSessionsContainer) return;
  sportSessionsContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted)">Chargement de l\'historique des séances...</div>';

  try {
    const res = await fetchSportSessionsData({ order: "desc", limit: 200 });
    cachedSessionsList = res.sessions || [];
    renderSportSessionsView();
  } catch (err) {
    sportSessionsContainer.innerHTML = `<div style="text-align:center; padding:30px; color:var(--color-danger)">Impossible de charger l'historique (${err.message}).</div>`;
  }
}

export function renderSportSessionsView() {
  if (!sportSessionsContainer) return;

  const filtered = cachedSessionsList.filter(s => {
    if (currentFilterStatus !== "all" && s.statut !== currentFilterStatus) {
      return false;
    }
    if (currentFilterType !== "all" && s.type_seance !== currentFilterType) {
      return false;
    }
    return true;
  });

  const typeOptions = [
    { id: "all", label: "Tous types" },
    { id: "EF", label: "🏃 EF" },
    { id: "Sortie Longue", label: "🏔️ Sortie Longue" },
    { id: "Fractionné", label: "⚡ Fractionné" },
    { id: "Renforcement", label: "🏋️ Renfo" },
    { id: "Course", label: "👟 Course" },
    { id: "Vitesse", label: "🚀 Vitesse" },
    { id: "Tempo", label: "🔥 Tempo" },
    { id: "Récup", label: "🌱 Récup" },
  ];

  const statusOptions = [
    { id: "all", label: "Tous statuts" },
    { id: "Réalisé", label: "✅ Réalisé" },
    { id: "Prévu", label: "📅 Prévu" },
  ];

  let html = `
    <!-- Filtres Rapides -->
    <div style="margin-bottom: 12px;">
      <div style="font-size:0.75rem; font-weight:800; text-transform:uppercase; color:var(--color-text-muted); margin-bottom:6px;">Type de séance</div>
      <div class="sport-filter-bar" id="session-type-filter-bar">
        ${typeOptions.map(opt => `
          <button type="button" class="sport-filter-pill ${currentFilterType === opt.id ? "active" : ""}" data-filter-type="${opt.id}">
            ${opt.label}
          </button>
        `).join("")}
      </div>

      <div style="font-size:0.75rem; font-weight:800; text-transform:uppercase; color:var(--color-text-muted); margin-bottom:6px;">Statut</div>
      <div class="sport-filter-bar" id="session-status-filter-bar">
        ${statusOptions.map(opt => `
          <button type="button" class="sport-filter-pill ${currentFilterStatus === opt.id ? "active" : ""}" data-filter-status="${opt.id}">
            ${opt.label}
          </button>
        `).join("")}
      </div>
    </div>

    <!-- Compteur -->
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; font-size:0.82rem; color:var(--color-text-secondary); font-weight:700;">
      <span>${filtered.length} séance${filtered.length > 1 ? "s" : ""} trouvée${filtered.length > 1 ? "s" : ""}</span>
      <span style="font-size:0.75rem; color:var(--color-text-muted);">Tri antichronologique</span>
    </div>
  `;

  if (filtered.length === 0) {
    html += `
      <div class="sport-session-card" style="text-align:center; padding:30px 16px;">
        <div style="font-size:2rem; margin-bottom:8px;">🔍</div>
        <p style="color:var(--color-text-secondary);">Aucune séance ne correspond aux filtres sélectionnés.</p>
      </div>
    `;
    sportSessionsContainer.innerHTML = html;
    attachSessionsFiltersHandlers();
    return;
  }

  html += filtered.map((s, idx) => {
    const isRealise = s.statut === "Réalisé";
    const statusClass = isRealise ? "realise" : (s.statut === "Repos" ? "repos" : "prevu");
    const statusLabel = s.statut || "Prévu";
    const typeCls = getTypeClass(s.type_seance);
    const typeEmoji = getTypeEmoji(s.type_seance);
    const dateFormatted = formatDateFr(s.date);

    const mainMetric = s.distance_km ? `${s.distance_km} km` : (s.duree_secondes ? formatDuration(s.duree_secondes) : "");
    const paceFormatted = s.allure_formatted || s.allure_cible || null;
    const isPainAlert = hasPainAlert(s.remarques) || hasPainAlert(s.notes);

    return `
      <div class="session-accordion-card" data-session-idx="${idx}" data-session-date="${s.date}" data-session-type="${s.type_seance}">
        <div class="session-accordion-header">
          <div class="session-header-left">
            <div class="session-date-badge">${dateFormatted}</div>
            <div style="display:flex; align-items:center; gap:8px; margin-top:4px; flex-wrap:wrap;">
              <span class="session-type-pill ${typeCls}">${typeEmoji} ${s.type_seance || "Course"}</span>
              <span style="font-size:0.75rem; color:var(--color-text-muted); font-weight:600;">Semaine ${s.semaine}</span>
              <span class="badge-status ${statusClass}" style="font-size:0.68rem; padding:1px 6px;">${statusLabel}</span>
              ${s.charge_rpe ? `<span style="font-size:0.75rem; background:rgba(59, 130, 246, 0.15); color:var(--color-accent); font-weight:700; padding:1px 6px; border-radius:6px;">🔥 RPE ${s.charge_rpe}</span>` : ""}
              ${s.meteo_note ? `<span style="font-size:0.75rem; background:rgba(255, 255, 255, 0.05); color:var(--color-text); font-weight:600; padding:1px 6px; border-radius:6px;">${getMeteoBadge(s.meteo_note)}</span>` : ""}
              ${isPainAlert ? '<span style="font-size:0.72rem; padding:1px 6px; border-radius:6px; background:rgba(239, 68, 68, 0.2); color:#ef4444; font-weight:800;">⚠️ Tibia/Douleur</span>' : ''}
            </div>
          </div>
          <div class="session-header-right">
            ${mainMetric ? `<span class="session-key-metric">${mainMetric}</span>` : ""}
            <div class="session-chevron">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="6 9 12 15 18 9"></polyline>
              </svg>
            </div>
          </div>
        </div>

        <div class="session-accordion-body" style="display:none;">
          <div class="sport-metrics-grid" style="margin-top:12px;">
            <div class="sport-metric-box">
              <div class="sport-metric-label">Distance</div>
              <div class="sport-metric-val">${s.distance_km ? s.distance_km : "-"}<span class="sport-metric-unit">${s.distance_km ? " km" : ""}</span></div>
            </div>

            <div class="sport-metric-box">
              <div class="sport-metric-label">Durée</div>
              <div class="sport-metric-val" style="font-size:0.95rem;">${formatDuration(s.duree_secondes) || "-"}</div>
            </div>

            <div class="sport-metric-box">
              <div class="sport-metric-label">${isRealise ? "Allure Moy" : "Allure Cible"}</div>
              <div class="sport-metric-val" style="font-size:0.95rem;">${paceFormatted || "-"}</div>
            </div>

            <div class="sport-metric-box">
              <div class="sport-metric-label">Vitesse</div>
              <div class="sport-metric-val">${s.vitesse_kmh ? s.vitesse_kmh : (s.vitesse_cible || "-")}<span class="sport-metric-unit">${s.vitesse_kmh ? " km/h" : ""}</span></div>
            </div>

            <div class="sport-metric-box">
              <div class="sport-metric-label">D+</div>
              <div class="sport-metric-val">${s.denivele_d_plus ? "+" + s.denivele_d_plus : "0"}<span class="sport-metric-unit"> m</span></div>
            </div>

            <div class="sport-metric-box">
              <div class="sport-metric-label">Km-Effort</div>
              <div class="sport-metric-val">${s.km_effort || "-"}</div>
            </div>

            <div class="sport-metric-box">
              <div class="sport-metric-label">RPE</div>
              <div class="sport-metric-val" style="color:${s.ressenti_rpe ? getRpeColor(s.ressenti_rpe) : 'inherit'}">
                ${s.ressenti_rpe ? s.ressenti_rpe : "-"}<span class="sport-metric-unit">${s.ressenti_rpe ? "/10" : ""}</span>
              </div>
            </div>

            <div class="sport-metric-box">
              <div class="sport-metric-label">Charge RPE</div>
              <div class="sport-metric-val" style="font-weight:700; color:var(--color-accent);">${s.charge_rpe ? s.charge_rpe : "-"}</div>
            </div>

            <div class="sport-metric-box">
              <div class="sport-metric-label">Météo</div>
              <div class="sport-metric-val" style="font-size:0.92rem;">${s.meteo_note ? getMeteoBadge(s.meteo_note) : "-"}</div>
            </div>

            <div class="sport-metric-box">
              <div class="sport-metric-label">FC Moy / Max</div>
              <div class="sport-metric-val" style="font-size:0.88rem;">${s.fc_moyenne ? s.fc_moyenne + " bpm" : "-"}${s.fc_max ? "<span style='font-size:0.75rem; color:var(--color-text-muted)'> / " + s.fc_max + "</span>" : ""}</div>
            </div>
          </div>

          ${s.programme ? `
            <div class="sport-details-block">
              <div class="sport-details-label">Programme Technique</div>
              <div>${s.programme}</div>
            </div>
          ` : ""}

          ${s.remarques ? `
            <div class="sport-details-block" style="border-left-color:${isPainAlert ? '#dc2626' : 'var(--color-accent)'}; ${isPainAlert ? 'background:rgba(239, 68, 68, 0.05);' : ''}">
              <div class="sport-details-label" style="${isPainAlert ? 'color:#dc2626;' : ''}">
                ${isPainAlert ? '⚠️ Remarques & Sensations (Vigilance Périostite)' : 'Remarques & Sensations'}
              </div>
              <div>${s.remarques}</div>
            </div>
          ` : ""}

          ${s.strava_id ? `
            <div style="font-size:0.72rem; color:var(--color-text-muted); text-align:right; margin-top:6px;">
              🔗 Synchronisé depuis Strava (#${s.strava_id})
            </div>
          ` : ""}

          <div class="session-actions-bar" style="display:flex; justify-content:flex-end; gap:8px; margin-top:14px; padding-top:12px; border-top:1px solid rgba(255,255,255,0.08);">
            <button type="button" class="btn-action-edit-session btn-secondary" data-session-id="${s.id || ""}" style="display:inline-flex; align-items:center; gap:6px; font-size:0.82rem; padding:6px 12px; border-radius:8px; cursor:pointer;">
              ✏️ Modifier
            </button>
            <button type="button" class="btn-action-delete-session" data-session-id="${s.id || ""}" style="display:inline-flex; align-items:center; gap:6px; font-size:0.82rem; padding:6px 12px; border-radius:8px; color:#ef4444; background:rgba(239, 68, 68, 0.1); border:1px solid rgba(239, 68, 68, 0.2); cursor:pointer;">
              🗑️ Supprimer
            </button>
          </div>
        </div>
      </div>
    `;
  }).join("");

  sportSessionsContainer.innerHTML = html;
  attachSessionsFiltersHandlers();
  attachAccordionToggles(sportSessionsContainer, ".session-accordion-card", ".session-accordion-header", ".session-accordion-body");
  attachSessionActionHandlers();
}

function attachSessionsFiltersHandlers() {
  const typeBar = document.getElementById("session-type-filter-bar");
  if (typeBar) {
    typeBar.querySelectorAll(".sport-filter-pill").forEach(btn => {
      btn.addEventListener("click", () => {
        currentFilterType = btn.getAttribute("data-filter-type");
        renderSportSessionsView();
      });
    });
  }

  const statusBar = document.getElementById("session-status-filter-bar");
  if (statusBar) {
    statusBar.querySelectorAll(".sport-filter-pill").forEach(btn => {
      btn.addEventListener("click", () => {
        currentFilterStatus = btn.getAttribute("data-filter-status");
        renderSportSessionsView();
      });
    });
  }
}

function attachSessionActionHandlers() {
  if (!sportSessionsContainer) return;

  sportSessionsContainer.querySelectorAll(".btn-action-edit-session").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const sessionId = btn.getAttribute("data-session-id");
      const session = cachedSessionsList.find(item => String(item.id) === String(sessionId));
      if (session) {
        openEditSessionModal(session);
      } else {
        showToastError("Séance introuvable pour modification.", "Erreur");
      }
    });
  });

  sportSessionsContainer.querySelectorAll(".btn-action-delete-session").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const sessionId = btn.getAttribute("data-session-id");
      const session = cachedSessionsList.find(item => String(item.id) === String(sessionId));
      if (!sessionId) {
        showToastError("Impossible de supprimer : ID de séance introuvable.", "Erreur");
        return;
      }

      const dateStr = session ? formatDateFr(session.date) : "cette date";
      const typeStr = session ? (session.type_seance || "Séance") : "Séance";
      if (!confirm(`Voulez-vous vraiment supprimer la séance "${typeStr}" du ${dateStr} ?\n\nCette action est irréversible et recalculera automatiquement vos bilans hebdomadaires.`)) {
        return;
      }

      const oldText = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = "⏳ Suppression...";

      try {
        await deleteSportSession(sessionId);
        showToastSuccess(`La séance du ${dateStr} a été supprimée et vos bilans ont été recalculés.`, "Séance supprimée");
        await fetchSportSessions();
        if (typeof fetchSportToday === "function") fetchSportToday();
        if (typeof fetchSportSummaries === "function") fetchSportSummaries();
        if (typeof fetchSportDashboard === "function") fetchSportDashboard();
        window.dispatchEvent(new CustomEvent("sport-data-updated"));
      } catch (err) {
        showToastError("Erreur lors de la suppression : " + err.message, "Erreur");
        btn.disabled = false;
        btn.innerHTML = oldText;
      }
    });
  });
}

function openEditSessionModal(session) {
  const modal = document.getElementById("modal-edit-sport-session");
  if (!modal) return;

  const idInput = document.getElementById("edit-session-id");
  const dateInput = document.getElementById("edit-session-date");
  const dateBadge = document.getElementById("edit-session-date-badge");
  const typeSelect = document.getElementById("edit-session-type");
  const statutSelect = document.getElementById("edit-session-statut");
  const distInput = document.getElementById("edit-session-distance");
  const dplusInput = document.getElementById("edit-session-dplus");
  const dureeMinInput = document.getElementById("edit-session-duree-min");
  const dureeSecInput = document.getElementById("edit-session-duree-sec");
  const rpeInput = document.getElementById("edit-session-rpe");
  const meteoInput = document.getElementById("edit-session-meteo");
  const fcMoyInput = document.getElementById("edit-session-fc-moy");
  const fcMaxInput = document.getElementById("edit-session-fc-max");
  const progInput = document.getElementById("edit-session-programme");
  const remTextarea = document.getElementById("edit-session-remarques");
  const errBox = document.getElementById("edit-session-error-msg");

  if (errBox) {
    errBox.style.display = "none";
    errBox.textContent = "";
  }

  idInput.value = session.id || "";
  if (dateInput) dateInput.value = session.date || "";
  if (dateBadge) dateBadge.textContent = formatDateFr(session.date);
  typeSelect.value = session.type_seance || "EF";
  statutSelect.value = session.statut || "Réalisé";
  distInput.value = session.distance_km != null ? session.distance_km : "";
  dplusInput.value = session.denivele_d_plus != null ? session.denivele_d_plus : "";

  if (session.duree_secondes) {
    const mins = Math.floor(session.duree_secondes / 60);
    const secs = session.duree_secondes % 60;
    dureeMinInput.value = mins || "";
    dureeSecInput.value = secs || "";
  } else {
    dureeMinInput.value = "";
    dureeSecInput.value = "";
  }

  rpeInput.value = session.ressenti_rpe != null ? session.ressenti_rpe : "";
  meteoInput.value = session.meteo_note != null ? session.meteo_note : "";
  fcMoyInput.value = session.fc_moyenne != null ? session.fc_moyenne : "";
  fcMaxInput.value = session.fc_max != null ? session.fc_max : "";
  progInput.value = session.programme || "";
  remTextarea.value = session.remarques || session.notes || "";

  modal.classList.add("active");
}

function closeEditSessionModal() {
  const modal = document.getElementById("modal-edit-sport-session");
  if (modal) modal.classList.remove("active");
}

async function saveEditedSession() {
  const idInput = document.getElementById("edit-session-id");
  const sessionId = idInput ? idInput.value : null;
  const errBox = document.getElementById("edit-session-error-msg");
  const saveBtn = document.getElementById("btn-save-edit-session");

  if (!sessionId) {
    if (errBox) {
      errBox.textContent = "ID de séance introuvable.";
      errBox.style.display = "block";
    }
    return;
  }

  const dateInput = document.getElementById("edit-session-date");
  const dateVal = dateInput ? dateInput.value : "";
  const typeVal = document.getElementById("edit-session-type").value;
  const statutVal = document.getElementById("edit-session-statut").value;
  const distStr = document.getElementById("edit-session-distance").value.trim();
  const dplusStr = document.getElementById("edit-session-dplus").value.trim();
  const minStr = document.getElementById("edit-session-duree-min").value.trim();
  const secStr = document.getElementById("edit-session-duree-sec").value.trim();
  const rpeStr = document.getElementById("edit-session-rpe").value.trim();
  const meteoStr = document.getElementById("edit-session-meteo").value.trim();
  const fcMoyStr = document.getElementById("edit-session-fc-moy").value.trim();
  const fcMaxStr = document.getElementById("edit-session-fc-max").value.trim();
  const progVal = document.getElementById("edit-session-programme").value.trim();
  const remVal = document.getElementById("edit-session-remarques").value.trim();

  let totalSec = null;
  if (minStr !== "" || secStr !== "") {
    const mins = parseInt(minStr, 10) || 0;
    const secs = parseInt(secStr, 10) || 0;
    totalSec = mins * 60 + secs;
  }

  const payload = {
    type_seance: typeVal,
    statut: statutVal,
    distance_km: distStr !== "" ? parseFloat(distStr) : null,
    duree_secondes: totalSec,
    denivele_d_plus: dplusStr !== "" ? parseInt(dplusStr, 10) : 0,
    ressenti_rpe: rpeStr !== "" ? parseInt(rpeStr, 10) : null,
    meteo_note: meteoStr !== "" ? parseInt(meteoStr, 10) : null,
    fc_moyenne: fcMoyStr !== "" ? parseInt(fcMoyStr, 10) : null,
    fc_max: fcMaxStr !== "" ? parseInt(fcMaxStr, 10) : null,
    programme: progVal,
    remarques: remVal,
  };

  if (dateVal) {
    payload.date = dateVal;
  }

  const oldBtnText = saveBtn.textContent;
  saveBtn.disabled = true;
  saveBtn.textContent = "Enregistrement en cours...";

  try {
    await patchSportSessionById(sessionId, payload);
    closeEditSessionModal();
    showToastSuccess("Séance modifiée avec succès et bilans mis à jour.", "Séance mise à jour");
    // Rafraîchir les vues
    await fetchSportSessions();
    if (typeof fetchSportToday === "function") fetchSportToday();
    if (typeof fetchSportSummaries === "function") fetchSportSummaries();
    if (typeof fetchSportDashboard === "function") fetchSportDashboard();
    window.dispatchEvent(new CustomEvent("sport-data-updated"));
  } catch (err) {
    if (errBox) {
      errBox.textContent = "Erreur lors de la modification : " + err.message;
      errBox.style.display = "block";
    }
    showToastError("Erreur lors de la modification : " + err.message, "Échec");
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = oldBtnText;
  }
}

function openCreateSessionModal() {
  const modal = document.getElementById("modal-create-sport-session");
  if (!modal) return;

  const dateInput = document.getElementById("create-session-date");
  const typeSelect = document.getElementById("create-session-type");
  const statutSelect = document.getElementById("create-session-statut");
  const distInput = document.getElementById("create-session-distance");
  const dplusInput = document.getElementById("create-session-dplus");
  const dureeMinInput = document.getElementById("create-session-duree-min");
  const dureeSecInput = document.getElementById("create-session-duree-sec");
  const rpeInput = document.getElementById("create-session-rpe");
  const meteoInput = document.getElementById("create-session-meteo");
  const fcMoyInput = document.getElementById("create-session-fc-moy");
  const progInput = document.getElementById("create-session-programme");
  const remTextarea = document.getElementById("create-session-remarques");
  const errBox = document.getElementById("create-session-error-msg");

  if (errBox) {
    errBox.style.display = "none";
    errBox.textContent = "";
  }

  const todayStr = new Date().toISOString().split("T")[0];
  if (dateInput) dateInput.value = todayStr;
  if (typeSelect) typeSelect.value = "EF";
  if (statutSelect) statutSelect.value = "Réalisé";
  if (distInput) distInput.value = "";
  if (dplusInput) dplusInput.value = "";
  if (dureeMinInput) dureeMinInput.value = "";
  if (dureeSecInput) dureeSecInput.value = "";
  if (rpeInput) rpeInput.value = "";
  if (meteoInput) meteoInput.value = "";
  if (fcMoyInput) fcMoyInput.value = "";
  if (progInput) progInput.value = "";
  if (remTextarea) remTextarea.value = "";

  modal.classList.add("active");
}

function closeCreateSessionModal() {
  const modal = document.getElementById("modal-create-sport-session");
  if (modal) modal.classList.remove("active");
}

async function saveCreatedSession() {
  const errBox = document.getElementById("create-session-error-msg");
  const saveBtn = document.getElementById("btn-save-create-session");

  const dateVal = document.getElementById("create-session-date").value;
  if (!dateVal) {
    if (errBox) {
      errBox.textContent = "Veuillez sélectionner une date pour la séance.";
      errBox.style.display = "block";
    }
    return;
  }

  const typeVal = document.getElementById("create-session-type").value;
  const statutVal = document.getElementById("create-session-statut").value;
  const distStr = document.getElementById("create-session-distance").value.trim();
  const dplusStr = document.getElementById("create-session-dplus").value.trim();
  const minStr = document.getElementById("create-session-duree-min").value.trim();
  const secStr = document.getElementById("create-session-duree-sec").value.trim();
  const rpeStr = document.getElementById("create-session-rpe").value.trim();
  const meteoStr = document.getElementById("create-session-meteo") ? document.getElementById("create-session-meteo").value.trim() : "";
  const fcMoyStr = document.getElementById("create-session-fc-moy").value.trim();
  const progVal = document.getElementById("create-session-programme").value.trim();
  const remVal = document.getElementById("create-session-remarques").value.trim();

  let totalSec = null;
  if (minStr !== "" || secStr !== "") {
    const mins = parseInt(minStr, 10) || 0;
    const secs = parseInt(secStr, 10) || 0;
    totalSec = mins * 60 + secs;
  }

  const payload = {
    date: dateVal,
    statut: statutVal,
    type_seance: typeVal,
    distance_km: distStr !== "" ? parseFloat(distStr) : null,
    duree_secondes: totalSec,
    denivele_d_plus: dplusStr !== "" ? parseInt(dplusStr, 10) : 0,
    ressenti_rpe: rpeStr !== "" ? parseInt(rpeStr, 10) : null,
    meteo_note: meteoStr !== "" ? parseInt(meteoStr, 10) : null,
    fc_moyenne: fcMoyStr !== "" ? parseInt(fcMoyStr, 10) : null,
    programme: progVal,
    remarques: remVal,
    notes: remVal,
  };

  const oldBtnText = saveBtn.textContent;
  saveBtn.disabled = true;
  saveBtn.textContent = "Création en cours...";

  try {
    await createSportSession(payload);
    closeCreateSessionModal();
    showToastSuccess("Séance enregistrée avec succès.", "Nouvelle séance créée");
    await fetchSportSessions();
    if (typeof fetchSportToday === "function") fetchSportToday();
    if (typeof fetchSportSummaries === "function") fetchSportSummaries();
    if (typeof fetchSportDashboard === "function") fetchSportDashboard();
    window.dispatchEvent(new CustomEvent("sport-data-updated"));
  } catch (err) {
    if (errBox) {
      errBox.textContent = "Erreur lors de la création : " + err.message;
      errBox.style.display = "block";
    }
    showToastError("Erreur lors de la création : " + err.message, "Échec");
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = oldBtnText;
  }
}

// ==========================================================================
// HISTORIQUE DES SEMAINES & SYNTHÈSE (Étape 4)
// ==========================================================================

export async function fetchSportSummaries() {
  if (!sportSummariesContainer) return;
  sportSummariesContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted)">Chargement des synthèses hebdomadaires...</div>';

  try {
    const res = await fetchSportSummariesData({ order: "desc", include_sessions: true });
    renderSportSummariesView(res.summaries || []);
  } catch (err) {
    sportSummariesContainer.innerHTML = `<div style="text-align:center; padding:30px; color:var(--color-danger)">Impossible de charger les synthèses (${err.message}).</div>`;
  }
}

export function renderSportSummariesView(summaries) {
  if (!sportSummariesContainer) return;

  if (!summaries || summaries.length === 0) {
    sportSummariesContainer.innerHTML = `
      <div class="sport-session-card" style="text-align:center; padding:30px 16px;">
        <div style="font-size:2rem; margin-bottom:8px;">📅</div>
        <p style="color:var(--color-text-secondary);">Aucune synthèse de semaine trouvée dans le Google Sheet.</p>
      </div>
    `;
    return;
  }

  let html = `
    <div style="margin-bottom:14px;">
      <h3 style="font-size:1.05rem; font-weight:800; color:var(--color-text); margin-bottom:4px;">Synthèses Hebdomadaires</h3>
      <p style="font-size:0.82rem; color:var(--color-text-secondary); line-height:1.4;">
        Bilan d'entraînement, volume, charge RPE et diagnostic de progression du coach Otis. Dépliez chaque semaine pour voir ses séances.
      </p>
    </div>
  `;

  html += summaries.map((item, sIdx) => {
    const sum = item.summary;
    const seances = item.seances || [];

    const alerte = sum.alerte_securite || "";
    let safetyCls = "neutre";
    if (alerte.includes("Blessure") || alerte.includes("Risque")) safetyCls = "risque";
    else if (alerte.includes("Vigilance")) safetyCls = "vigilance";
    else if (alerte.includes("Saine")) safetyCls = "saine";

    return `
      <div class="summary-accordion-card">
        <div class="summary-accordion-header">
          <div class="summary-header-row">
            <div class="summary-title">
              <span>📅 Semaine ${sum.semaine}</span>
              <span style="font-size:0.8rem; font-weight:600; color:var(--color-text-muted);">(${sum.annee})</span>
              <span class="badge-safety ${safetyCls}">${alerte || "Suivi normal"}</span>
            </div>
            <div class="summary-chevron">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="6 9 12 15 18 9"></polyline>
              </svg>
            </div>
          </div>

          <div class="summary-metrics-strip">
            <div class="summary-metric-item"><strong>${sum.km_total} km</strong></div>
            <div class="summary-metric-item">⛰️ +${sum.d_plus_total} m</div>
            <div class="summary-metric-item">⚡ <strong>${sum.km_effort_total}</strong> km-e</div>
            <div class="summary-metric-item">⏱️ ${sum.allure_moyenne_formatted || "-"}</div>
            <div class="summary-metric-item">🔥 RPE ${sum.charge_rpe_totale}</div>
            <div class="summary-metric-item">🏃 ${sum.nb_seances} séance${sum.nb_seances > 1 ? "s" : ""}</div>
          </div>
        </div>

        <div class="summary-accordion-body" style="display:none;">
          <div style="background:var(--color-surface); border-radius:var(--radius-sm); padding:10px 12px; margin-bottom:12px; border:1px solid var(--color-border); font-size:0.82rem; display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px;">
            <div>
              <span style="color:var(--color-text-muted);">Évolution Volume (Km-Effort) :</span>
              <strong>${sum.evolution_volume_pct !== null && sum.evolution_volume_pct !== undefined ? (sum.evolution_volume_pct > 0 ? "+" : "") + sum.evolution_volume_pct + "%" : "1ère semaine"}</strong>
            </div>
            <div>
              <span style="color:var(--color-text-muted);">Plafond S+1 conseillé :</span>
              <strong>${sum.plafond_conseille_s_plus_1 || "-"} km-effort</strong>
            </div>
          </div>

          <div style="font-size:0.78rem; font-weight:800; text-transform:uppercase; color:var(--color-text-muted); margin-bottom:8px;">
            Séances de la Semaine (${seances.length})
          </div>

          ${seances.length === 0 ? `
            <div style="font-size:0.82rem; color:var(--color-text-muted); padding:8px 0;">Aucune séance détaillée enregistrée pour cette semaine.</div>
          ` : `
            <div style="display:flex; flex-direction:column; gap:8px;">
              ${seances.map(s => {
                const typeCls = getTypeClass(s.type_seance);
                const typeEmoji = getTypeEmoji(s.type_seance);
                const isRealise = s.statut === "Réalisé";
                const dateFr = formatDateFr(s.date);
                return `
                  <div style="background:var(--color-surface); border-radius:8px; border:1px solid var(--color-border); padding:8px 10px; font-size:0.82rem;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                      <div style="display:flex; align-items:center; gap:6px;">
                        <span style="font-weight:700;">${dateFr}</span>
                        <span class="session-type-pill ${typeCls}" style="font-size:0.68rem; padding:1px 6px;">${typeEmoji} ${s.type_seance}</span>
                      </div>
                      <span class="badge-status ${isRealise ? "realise" : "prevu"}" style="font-size:0.65rem; padding:1px 5px;">${s.statut}</span>
                    </div>
                    <div style="display:flex; justify-content:space-between; align-items:center; color:var(--color-text-secondary); font-size:0.78rem;">
                      <span>
                        ${s.distance_km ? `<strong>${s.distance_km} km</strong> · ` : ""}
                        ${s.duree_secondes ? formatDuration(s.duree_secondes) + " · " : ""}
                        ${s.allure_formatted ? s.allure_formatted + "/km" : ""}
                      </span>
                      <span>${s.ressenti_rpe ? `<strong style="color:${getRpeColor(s.ressenti_rpe)}">RPE ${s.ressenti_rpe}/10</strong>` : ""}</span>
                    </div>
                    ${s.programme ? `<div style="font-size:0.75rem; color:var(--color-text-muted); margin-top:4px; font-style:italic;">${s.programme}</div>` : ""}
                    ${s.remarques ? `<div style="font-size:0.75rem; color:var(--color-accent); margin-top:2px;">💬 ${s.remarques}</div>` : ""}
                  </div>
                `;
              }).join("")}
            </div>
          `}
        </div>
      </div>
    `;
  }).join("");

  sportSummariesContainer.innerHTML = html;
  attachAccordionToggles(sportSummariesContainer, ".summary-accordion-card", ".summary-accordion-header", ".summary-accordion-body");
}

function attachAccordionToggles(container, cardSelector, headerSelector, bodySelector) {
  const cards = container.querySelectorAll(cardSelector);
  cards.forEach(card => {
    const header = card.querySelector(headerSelector);
    const body = card.querySelector(bodySelector);
    if (header && body) {
      header.addEventListener("click", () => {
        const isOpen = card.classList.toggle("open");
        body.style.display = isOpen ? "block" : "none";
      });
    }
  });
}

export function initSportView() {
  if (tabSportToday) tabSportToday.addEventListener("click", () => switchSportSubview("today"));
  if (tabSportSessions) tabSportSessions.addEventListener("click", () => switchSportSubview("sessions"));
  if (tabSportSummaries) tabSportSummaries.addEventListener("click", () => switchSportSubview("summaries"));
  if (tabSportImport) tabSportImport.addEventListener("click", () => switchSportSubview("import"));
  if (tabSportDash) tabSportDash.addEventListener("click", () => switchSportSubview("dashboard"));
  if (tabSportGamification) tabSportGamification.addEventListener("click", () => switchSportSubview("gamification"));

  // Ingestion Visuelle de Course (Header & Sous-vue Dédiée)
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

  // Dropzone de la sous-vue Importer
  const importDropzone = document.getElementById("sport-import-dropzone");
  const importFileInput = document.getElementById("file-sport-import-view-input");
  if (importDropzone && importFileInput) {
    importDropzone.addEventListener("click", () => importFileInput.click());
    importFileInput.addEventListener("change", (e) => {
      const file = e.target.files && e.target.files[0];
      if (file) {
        handleSportScreenshotUpload(file);
        importFileInput.value = "";
      }
    });

    // Drag & Drop
    importDropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      importDropzone.style.borderColor = "var(--color-primary-dark)";
      importDropzone.style.background = "rgba(37, 99, 235, 0.1)";
    });
    importDropzone.addEventListener("dragleave", () => {
      importDropzone.style.borderColor = "var(--color-primary)";
      importDropzone.style.background = "rgba(37, 99, 235, 0.04)";
    });
    importDropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      importDropzone.style.borderColor = "var(--color-primary)";
      importDropzone.style.background = "rgba(37, 99, 235, 0.04)";
      const file = e.dataTransfer?.files?.[0];
      if (file) {
        handleSportScreenshotUpload(file);
      }
    });
  }

  // Support du collage (Paste / Ctrl+V) d'une capture d'écran sur l'onglet Sport
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

  // Écouteurs pour le modal d'édition manuelle de séance
  const modal = document.getElementById("modal-edit-sport-session");
  const cancelBtn = document.getElementById("btn-cancel-edit-session");
  const saveBtn = document.getElementById("btn-save-edit-session");
  if (cancelBtn) cancelBtn.addEventListener("click", closeEditSessionModal);
  if (saveBtn) saveBtn.addEventListener("click", saveEditedSession);
  if (modal) {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) closeEditSessionModal();
    });
  }

  // Écouteurs pour le modal de création manuelle de séance
  const addBtn = document.getElementById("btn-add-sport-session-inline");
  const createModal = document.getElementById("modal-create-sport-session");
  const cancelCreateBtn = document.getElementById("btn-cancel-create-session");
  const saveCreateBtn = document.getElementById("btn-save-create-session");
  if (addBtn) addBtn.addEventListener("click", openCreateSessionModal);
  if (cancelCreateBtn) cancelCreateBtn.addEventListener("click", closeCreateSessionModal);
  if (saveCreateBtn) saveCreateBtn.addEventListener("click", saveCreatedSession);
  if (createModal) {
    createModal.addEventListener("click", (e) => {
      if (e.target === createModal) closeCreateSessionModal();
    });
  }

  // Rafraîchissement automatique si le chat effectue une modification de séance
  window.addEventListener("sport-data-updated", () => {
    if (state.currentSportSubview === "sessions") {
      fetchSportSessions();
    } else if (state.currentSportSubview === "today") {
      fetchSportToday();
    }
  });
}

