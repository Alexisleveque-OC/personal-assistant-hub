// Système Universel de Notifications Flottantes (Toasts) & Observabilité UI
// Remplace définitivement les alert() bloquants et les messages d'erreur muets

function getOrCreateToastContainer() {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "toast-container";
    container.setAttribute("aria-live", "polite");
    document.body.appendChild(container);
  }
  return container;
}

const DEFAULT_ICONS = {
  success: "✅",
  error: "❌",
  warning: "⚠️",
  info: "ℹ️"
};

const DEFAULT_TITLES = {
  success: "Succès",
  error: "Erreur",
  warning: "Attention",
  info: "Information"
};

/**
 * Affiche un toast flottant élégant et contextualisé.
 * @param {string} message - Message explicatif détaillé
 * @param {"success"|"error"|"warning"|"info"} [type="info"] - Catégorie de notification
 * @param {Object} [options]
 * @param {string} [options.title] - Titre court optionnel
 * @param {string} [options.icon] - Emoji / Icône personnalisée
 * @param {number} [options.duration] - Durée d'affichage en ms (défaut: 4000ms, 7000ms pour error)
 */
export function showToast(message, type = "info", { title = null, icon = null, duration = null } = {}) {
  const container = getOrCreateToastContainer();

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.setAttribute("role", type === "error" ? "alert" : "status");

  const displayIcon = icon || DEFAULT_ICONS[type] || "ℹ️";
  const displayTitle = title !== null ? title : (DEFAULT_TITLES[type] || "");
  const autoDuration = duration !== null ? duration : (type === "error" ? 7000 : 4500);

  toast.innerHTML = `
    <span class="toast-icon" aria-hidden="true">${displayIcon}</span>
    <div class="toast-content">
      ${displayTitle ? `<div class="toast-title">${escapeHtml(displayTitle)}</div>` : ""}
      <div class="toast-message">${escapeHtml(message)}</div>
    </div>
    <button class="toast-close" type="button" aria-label="Fermer la notification">×</button>
  `;

  const closeBtn = toast.querySelector(".toast-close");
  let timerId = null;

  const dismiss = () => {
    if (timerId) clearTimeout(timerId);
    toast.classList.add("toast-hiding");
    toast.addEventListener("transitionend", () => {
      toast.remove();
    }, { once: true });
    // Fallback de sécurité si transitionend ne se déclenche pas
    setTimeout(() => {
      if (toast.parentElement) toast.remove();
    }, 300);
  };

  closeBtn.addEventListener("click", dismiss);

  if (autoDuration > 0) {
    timerId = setTimeout(dismiss, autoDuration);
  }

  container.appendChild(toast);
  return { dismiss };
}

export function showToastSuccess(message, title = "Succès") {
  return showToast(message, "success", { title });
}

export function showToastError(message, title = "Erreur") {
  return showToast(message, "error", { title, duration: 8000 });
}

export function showToastInfo(message, title = "Information") {
  return showToast(message, "info", { title });
}

export function showToastWarning(message, title = "Attention") {
  return showToast(message, "warning", { title });
}

function escapeHtml(text) {
  if (typeof text !== "string") return String(text ?? "");
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}
