// Feuille « Journal & feedback » (sortie du Second cerveau à l'étape 7 de la refonte UX) : contenu inchangé.
// Échanges avec Otis (requête, réponse, latence) et correction envoyée pour l'auto-apprentissage.
import { fetchConversationLogs, postConversationFeedback } from "../api.js";

export async function loadConversationAuditLogs() {
  const listEl = document.getElementById("audit-logs-list");
  if (!listEl) return;

  listEl.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted)">Chargement du journal d\'audit...</div>';

  try {
    const data = await fetchConversationLogs({ limit: 40 });
    const logs = data.items || [];

    if (logs.length === 0) {
      listEl.innerHTML = `
        <div class="empty-state-card">
          <div style="font-size:2.5rem; margin-bottom:8px;">📜</div>
          <div style="font-weight:600; color:var(--text-primary)">Aucun échange enregistré</div>
          <p style="font-size:0.85rem; color:var(--text-secondary); margin-top:4px;">
            Les requêtes vocales et écrites apparaîtront ici avec leur latence et analyse.
          </p>
        </div>
      `;
      return;
    }

    listEl.innerHTML = "";
    logs.forEach((log) => {
      const isSuccess = log.status === "success";
      const latencyStr = log.latency_ms ? `${log.latency_ms} ms` : "-";
      const dateStr = log.created_at ? formatDateTime(log.created_at) : "";

      const card = document.createElement("div");
      card.className = "audit-card";
      card.innerHTML = `
        <div class="audit-card-header">
          <div style="display:flex; align-items:center; gap:8px;">
            <span class="audit-status-dot ${isSuccess ? "ok" : "err"}"></span>
            <span class="audit-intent-badge">${escapeHtml(log.intent || "inconnu")}</span>
            <span class="audit-matched-by">${escapeHtml(log.matched_by || "auto")}</span>
          </div>
          <span class="audit-date">${dateStr}</span>
        </div>

        <div class="audit-prompt">
          <strong>Vous :</strong> ${escapeHtml(log.user_prompt || "")}
        </div>

        <div class="audit-response">
          <strong>Otis :</strong> ${escapeHtml(log.spoken_response || log.error_message || "Aucune réponse")}
        </div>

        <div class="audit-footer">
          <div class="audit-meta-info">
            <span>⚡ ${latencyStr}</span>
            <span>🤖 ${escapeHtml(log.llm_model || "Flash")}</span>
          </div>
          <button class="btn-feedback-action" data-id="${log.id}">
            💬 Corriger / Signaler
          </button>
        </div>

        <div class="feedback-form-box" id="feedback-box-${log.id}" style="display:none;">
          <textarea class="form-input feedback-textarea" placeholder="Expliquez ce qui n'allait pas ou la bonne réponse attendue..."></textarea>
          <div style="display:flex; gap:8px; justify-content:flex-end; margin-top:6px;">
            <button type="button" class="btn-secondary btn-cancel-feedback" style="font-size:0.75rem; padding:4px 8px;">Annuler</button>
            <button type="button" class="btn-primary btn-submit-feedback" style="font-size:0.75rem; padding:4px 8px;">Envoyer correction</button>
          </div>
        </div>
      `;

      // Gestion ouverture et soumission feedback
      const btnFeedback = card.querySelector(".btn-feedback-action");
      const boxFeedback = card.querySelector(`#feedback-box-${log.id}`);
      const btnCancel = card.querySelector(".btn-cancel-feedback");
      const btnSubmit = card.querySelector(".btn-submit-feedback");
      const textarea = card.querySelector(".feedback-textarea");

      btnFeedback.addEventListener("click", () => {
        boxFeedback.style.display = boxFeedback.style.display === "none" ? "block" : "none";
        if (boxFeedback.style.display === "block") textarea.focus();
      });

      btnCancel.addEventListener("click", () => {
        boxFeedback.style.display = "none";
      });

      btnSubmit.addEventListener("click", async () => {
        const note = textarea.value.trim();
        if (!note) return;
        try {
          await postConversationFeedback(log.id, {
            feedback_type: "correction",
            user_note: note,
          });
          boxFeedback.innerHTML = '<div style="color:var(--accent-teal); font-size:0.8rem; padding:6px 0;">✓ Correction enregistrée avec succès pour l\'auto-apprentissage !</div>';
        } catch (e) {
          alert("Erreur lors de l'enregistrement du feedback : " + e.message);
        }
      });

      listEl.appendChild(card);
    });
  } catch (err) {
    listEl.innerHTML = `<div style="text-align:center; padding:30px; color:var(--accent-rose)">Erreur de chargement : ${escapeHtml(err.message)}</div>`;
  }
}

function formatDateTime(isoString) {
  try {
    const d = new Date(isoString);
    return d.toLocaleDateString("fr-FR", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch (e) {
    return isoString;
  }
}

function escapeHtml(text) {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
