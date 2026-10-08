// Vue Second Cerveau & Journal d'Audit Conversationnel
import { state } from "../config.js";
import {
  fetchSecondBrainNotes,
  fetchSecondBrainStats,
  createSecondBrainNote,
  patchSecondBrainNote,
  deleteSecondBrainNote,
  fetchConversationLogs,
  postConversationFeedback,
} from "../api.js";

// Sélecteurs DOM principaux
let containerNotes = null;
let containerAudit = null;
let categoryPillsContainer = null;
let currentCategoryFilter = null;
let currentStatusFilter = "active";
let currentSearchQuery = "";
let currentBrainSubview = "notes"; // "notes" | "audit"

const CATEGORY_META = {
  dev_idea: { label: "À Développer", icon: "🛠️", color: "#3b82f6" },
  bug_report: { label: "Bugs & Fixes", icon: "🐛", color: "#ef4444" },
  thought: { label: "Pensées & Idées", icon: "💡", color: "#f59e0b" },
  preference: { label: "Préférences", icon: "🎯", color: "#8b5cf6" },
  task: { label: "Tâches", icon: "📋", color: "#10b981" },
  voyage: { label: "Voyages", icon: "🌴", color: "#06b6d4" },
  vacances: { label: "Vacances", icon: "✈️", color: "#06b6d4" },
  cuisine: { label: "Cuisine", icon: "🍳", color: "#f97316" },
  sport_coach: { label: "Coach Sport", icon: "🏃", color: "#ec4899" },
};

export function getCategoryMeta(cat) {
  const normalized = (cat || "").toLowerCase();
  return CATEGORY_META[normalized] || {
    label: cat.charAt(0).toUpperCase() + cat.slice(1),
    icon: "📌",
    color: "#64748b",
  };
}

export function initSecondBrainView() {
  containerNotes = document.getElementById("second-brain-notes-container");
  containerAudit = document.getElementById("second-brain-audit-container");
  categoryPillsContainer = document.getElementById("brain-category-pills");

  const tabNotes = document.getElementById("tab-brain-notes");
  const tabAudit = document.getElementById("tab-brain-audit");
  const btnNewNote = document.getElementById("btn-add-note-inline");
  const formNewNote = document.getElementById("form-add-note");
  const inputSearch = document.getElementById("brain-search-input");
  const statusFilterSelect = document.getElementById("brain-status-filter");

  // Bascule Notes / Audit
  if (tabNotes && tabAudit) {
    tabNotes.addEventListener("click", () => switchBrainSubview("notes"));
    tabAudit.addEventListener("click", () => switchBrainSubview("audit"));
  }

  // Filtrage par statut (actives / archivées)
  if (statusFilterSelect) {
    statusFilterSelect.addEventListener("change", (e) => {
      currentStatusFilter = e.target.value;
      loadSecondBrainNotes();
    });
  }

  // Recherche en direct
  if (inputSearch) {
    let debounceTimer = null;
    inputSearch.addEventListener("input", (e) => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        currentSearchQuery = e.target.value.trim();
        loadSecondBrainNotes();
      }, 300);
    });
  }

  // Toggle affichage formulaire d'ajout
  if (btnNewNote && formNewNote) {
    btnNewNote.addEventListener("click", () => {
      const isVisible = formNewNote.style.display !== "none";
      formNewNote.style.display = isVisible ? "none" : "block";
      if (!isVisible) {
        document.getElementById("note-content-input")?.focus();
      }
    });

    formNewNote.addEventListener("submit", async (e) => {
      e.preventDefault();
      const contentInput = document.getElementById("note-content-input");
      const categorySelect = document.getElementById("note-category-select");
      const content = contentInput ? contentInput.value.trim() : "";
      const category = categorySelect ? categorySelect.value : "thought";

      if (!content) return;

      try {
        await createSecondBrainNote({ content, category });
        if (contentInput) contentInput.value = "";
        formNewNote.style.display = "none";
        loadSecondBrainNotes();
        loadSecondBrainCategories();
      } catch (err) {
        alert("Erreur lors de l'enregistrement de la note : " + err.message);
      }
    });
  }
}

export function switchBrainSubview(subview) {
  currentBrainSubview = subview;
  const tabNotes = document.getElementById("tab-brain-notes");
  const tabAudit = document.getElementById("tab-brain-audit");

  if (tabNotes && tabAudit) {
    tabNotes.classList.toggle("active", subview === "notes");
    tabAudit.classList.toggle("active", subview === "audit");
  }

  if (containerNotes && containerAudit) {
    containerNotes.style.display = subview === "notes" ? "block" : "none";
    containerAudit.style.display = subview === "audit" ? "block" : "none";
  }

  const controlsNotes = document.getElementById("brain-notes-controls");
  if (controlsNotes) {
    controlsNotes.style.display = subview === "notes" ? "block" : "none";
  }

  if (subview === "notes") {
    loadSecondBrainNotes();
    loadSecondBrainCategories();
  } else {
    loadConversationAuditLogs();
  }
}

// ============================================================================
// 1. Gestion des Notes du Second Cerveau
// ============================================================================

export async function loadSecondBrainCategories() {
  if (!categoryPillsContainer) return;
  try {
    const stats = await fetchSecondBrainStats();
    categoryPillsContainer.innerHTML = "";

    // Pill "Toutes"
    const allTotal = Object.values(stats).reduce((a, b) => a + b, 0);
    const pillAll = document.createElement("button");
    pillAll.className = `cat-pill ${currentCategoryFilter === null ? "active" : ""}`;
    pillAll.innerHTML = `<span>Tout</span> <span class="pill-count">${allTotal}</span>`;
    pillAll.addEventListener("click", () => {
      currentCategoryFilter = null;
      updateActiveCategoryPill(pillAll);
      loadSecondBrainNotes();
    });
    categoryPillsContainer.appendChild(pillAll);

    // Découverte dynamique de tous les segments existants
    Object.keys(stats).forEach((cat) => {
      const count = stats[cat];
      const meta = getCategoryMeta(cat);
      const pill = document.createElement("button");
      pill.className = `cat-pill ${currentCategoryFilter === cat ? "active" : ""}`;
      pill.innerHTML = `<span>${meta.icon} ${meta.label}</span> <span class="pill-count">${count}</span>`;
      pill.addEventListener("click", () => {
        currentCategoryFilter = cat;
        updateActiveCategoryPill(pill);
        loadSecondBrainNotes();
      });
      categoryPillsContainer.appendChild(pill);
    });
  } catch (e) {
    console.warn("Impossible de charger les catégories du second cerveau :", e);
  }
}

function updateActiveCategoryPill(activePill) {
  if (!categoryPillsContainer) return;
  categoryPillsContainer.querySelectorAll(".cat-pill").forEach((p) => p.classList.remove("active"));
  activePill.classList.add("active");
}

export async function loadSecondBrainNotes() {
  if (!containerNotes) return;
  const listEl = document.getElementById("second-brain-list");
  if (!listEl) return;

  listEl.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted)">Chargement de vos notes...</div>';

  try {
    const data = await fetchSecondBrainNotes({
      category: currentCategoryFilter,
      status: currentStatusFilter || null,
      search: currentSearchQuery || null,
      limit: 100,
    });

    const notes = data.items || [];
    if (notes.length === 0) {
      listEl.innerHTML = `
        <div class="empty-state-card">
          <div style="font-size:2.5rem; margin-bottom:8px;">🧠</div>
          <div style="font-weight:600; color:var(--text-primary)">Aucune note trouvée</div>
          <p style="font-size:0.85rem; color:var(--text-secondary); margin-top:4px;">
            ${currentSearchQuery ? "Aucun résultat pour cette recherche." : "Dites « Otis, note que... » ou cliquez sur « + Ajouter » ci-dessus."}
          </p>
        </div>
      `;
      return;
    }

    listEl.innerHTML = "";
    notes.forEach((note) => {
      const meta = getCategoryMeta(note.category);
      const isDone = note.status === "done";

      const card = document.createElement("div");
      card.className = `note-card ${isDone ? "done" : ""}`;
      card.setAttribute("data-id", note.id);

      const dateStr = note.created_at ? formatDateTime(note.created_at) : "";

      card.innerHTML = `
        <div class="note-card-header">
          <span class="note-badge" style="background:${meta.color}20; color:${meta.color}; border:1px solid ${meta.color}40;">
            ${meta.icon} ${meta.label}
          </span>
          <span class="note-date">${dateStr}</span>
        </div>
        <div class="note-content ${isDone ? "text-done" : ""}">${escapeHtml(note.content)}</div>
        <div class="note-actions">
          <button class="btn-note-toggle ${isDone ? "btn-reopen" : "btn-complete"}" title="${isDone ? "Réactiver la note" : "Marquer comme fait"}">
            ${isDone ? "↺ Réactiver" : "✓ Fait"}
          </button>
          <button class="btn-note-delete" title="Supprimer la note">
            🗑️
          </button>
        </div>
      `;

      // Écouteur toggle statut
      const btnToggle = card.querySelector(".btn-note-toggle");
      btnToggle.addEventListener("click", async () => {
        const newStatus = isDone ? "active" : "done";
        try {
          await patchSecondBrainNote(note.id, { status: newStatus });
          loadSecondBrainNotes();
          loadSecondBrainCategories();
        } catch (err) {
          alert("Erreur mise à jour note : " + err.message);
        }
      });

      // Écouteur suppression
      const btnDelete = card.querySelector(".btn-note-delete");
      btnDelete.addEventListener("click", async () => {
        if (confirm("Supprimer définitivement cette note ?")) {
          try {
            await deleteSecondBrainNote(note.id);
            loadSecondBrainNotes();
            loadSecondBrainCategories();
          } catch (err) {
            alert("Erreur suppression note : " + err.message);
          }
        }
      });

      listEl.appendChild(card);
    });
  } catch (err) {
    listEl.innerHTML = `<div style="text-align:center; padding:30px; color:var(--accent-rose)">Erreur de chargement : ${escapeHtml(err.message)}</div>`;
  }
}

// ============================================================================
// 2. Gestion du Journal Conversationnel & Audit
// ============================================================================

export async function loadConversationAuditLogs() {
  if (!containerAudit) return;
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

// Helpers
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
