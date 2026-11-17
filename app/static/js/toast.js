// Système Universel de Notifications Flottantes (Toasts) & Observabilité UI
// Remplace définitivement les alert() bloquants et les messages d'erreur muets
// Refonte UX : cartes du design system (pastille d'icône SVG colorée par type), rendu DOM sans injection HTML.

const SVG_NS = "http://www.w3.org/2000/svg";

function getOrCreateToastContainer() {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "toast-stack";
    container.setAttribute("aria-live", "polite");
    document.body.appendChild(container);
  }
  return container;
}

// Tracé de l'icône de chaque type (coche, croix, point d'exclamation, i).
const ICON_PATHS = {
  success: "M6 12.5l4 4 8-9",
  error: "M7 7l10 10M17 7L7 17",
  warning: "M12 6v8M12 18h.01",
  info: "M12 11v7M12 6h.01",
};

const DEFAULT_TITLES = {
  success: "Succès",
  error: "Erreur",
  warning: "Attention",
  info: "Information"
};

function icon(type) {
  const badge = document.createElement("span");
  badge.className = "notice__icon";
  badge.setAttribute("aria-hidden", "true");
  const svg = document.createElementNS(SVG_NS, "svg");
  for (const [name, value] of Object.entries({
    viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "2.6",
    "stroke-linecap": "round", "stroke-linejoin": "round",
  })) svg.setAttribute(name, value);
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", ICON_PATHS[type] || ICON_PATHS.info);
  svg.append(path);
  badge.append(svg);
  return badge;
}

function textNode(tag, className, text) {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}

/**
 * Affiche un toast flottant élégant et contextualisé.
 * @param {string} message - Message explicatif détaillé
 * @param {"success"|"error"|"warning"|"info"} [type="info"] - Catégorie de notification
 * @param {Object} [options]
 * @param {string} [options.title] - Titre court optionnel
 * @param {number} [options.duration] - Durée d'affichage en ms (défaut: 4500ms, 7000ms pour error)
 * @param {{label: string, onClick: Function}} [options.action] - Bouton d'action (ex: « Annuler ») ; le toast se ferme au clic
 */
export function showToast(message, type = "info", { title = null, duration = null, action = null } = {}) {
  const container = getOrCreateToastContainer();
  const kind = ICON_PATHS[type] ? type : "info";

  const toast = document.createElement("div");
  toast.className = `notice notice--${kind}`;
  toast.setAttribute("role", kind === "error" ? "alert" : "status");

  const displayTitle = title !== null ? title : (DEFAULT_TITLES[kind] || "");
  const autoDuration = duration !== null ? duration : (kind === "error" ? 7000 : 4500);

  const content = document.createElement("div");
  content.className = "notice__content";
  if (displayTitle) content.append(textNode("div", "notice__title", displayTitle));
  content.append(textNode("div", "notice__text", String(message ?? "")));
  toast.append(icon(kind), content);

  let actionBtn = null;
  if (action) {
    actionBtn = textNode("button", "notice__action btn-undo-action", action.label);
    actionBtn.type = "button";
    toast.append(actionBtn);
  }

  const closeBtn = textNode("button", "notice__close", "×");
  closeBtn.type = "button";
  closeBtn.setAttribute("aria-label", "Fermer la notification");
  toast.append(closeBtn);

  let timerId = null;

  const dismiss = () => {
    if (timerId) clearTimeout(timerId);
    toast.classList.add("notice--leaving");
    toast.addEventListener("transitionend", () => {
      toast.remove();
    }, { once: true });
    // Fallback de sécurité si transitionend ne se déclenche pas
    setTimeout(() => {
      if (toast.parentElement) toast.remove();
    }, 300);
  };

  closeBtn.addEventListener("click", dismiss);

  if (actionBtn) {
    actionBtn.addEventListener("click", () => {
      dismiss();
      action.onClick();
    }, { once: true });
  }

  if (autoDuration > 0) {
    timerId = setTimeout(dismiss, autoDuration);
  }

  container.appendChild(toast);
  return { dismiss };
}

// `options` : duration, action (ex. duration 0 = reste affiché jusqu'à dismiss()).
export function showToastSuccess(message, title = "Succès", options = {}) {
  return showToast(message, "success", { title, ...options });
}

export function showToastError(message, title = "Erreur", options = {}) {
  return showToast(message, "error", { title, duration: 8000, ...options });
}

export function showToastInfo(message, title = "Information", options = {}) {
  return showToast(message, "info", { title, ...options });
}

export function showToastWarning(message, title = "Attention", options = {}) {
  return showToast(message, "warning", { title, ...options });
}
