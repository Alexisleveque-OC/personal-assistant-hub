// Feuille « Journal & feedback » (refonte UX, étape 7 suite ; contenu inchangé).
// Échanges avec Otis (requête, réponse, statut, latence, modèle) et correction envoyée pour l'auto-apprentissage.
import { fetchConversationLogs, postConversationFeedback } from "../api.js";
import { feedbackPayload, logCard } from "../journal_model.js";
import { showToastError } from "../toast.js";
import { button, el } from "./sport/dom.js";

const listContainer = document.getElementById("audit-logs-list");

function message(text, className = "muted") {
  return el("p", `shopping-note ${className}`, text);
}

export async function loadConversationAuditLogs() {
  if (!listContainer) return;
  listContainer.replaceChildren(message("Chargement du journal…"));
  try {
    const data = await fetchConversationLogs({ limit: 40 });
    const logs = data.items || [];
    if (!logs.length) {
      listContainer.replaceChildren(message("Aucun échange enregistré. Les requêtes vocales et écrites apparaîtront ici."));
      return;
    }
    const now = new Date();
    listContainer.replaceChildren(...logs.map((log) => logArticle(logCard(log, now))));
  } catch (err) {
    listContainer.replaceChildren(message(err.message || "Impossible de charger le journal.", "shopping-note--error"));
  }
}

function line(who, text) {
  const node = el("p", "journal-card__line");
  node.append(el("strong", null, `${who} : `), document.createTextNode(text));
  return node;
}

function feedbackForm(view, toggle) {
  const form = el("form", "journal-card__form");
  form.id = `journal-feedback-${view.id}`;
  form.hidden = true;
  const label = el("label", "sr-only", "Correction pour Otis");
  label.htmlFor = `journal-feedback-text-${view.id}`;
  const text = el("textarea", "textarea");
  text.id = label.htmlFor;
  text.rows = 3;
  text.placeholder = "Ce qui n'allait pas, ou la bonne réponse attendue…";
  const cancel = button("btn", "Annuler");
  const send = el("button", "btn btn--primary", "Envoyer");
  send.type = "submit";
  const actions = el("div", "journal-card__form-actions");
  actions.append(cancel, send);
  form.append(label, text, actions);

  const setOpen = (open) => {
    form.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    if (open) text.focus();
  };
  toggle.addEventListener("click", () => setOpen(form.hidden));
  cancel.addEventListener("click", () => {
    setOpen(false);
    toggle.focus();
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = feedbackPayload(text.value);
    if (!payload) {
      text.focus();
      return;
    }
    send.disabled = true;
    try {
      await postConversationFeedback(view.id, payload);
    } catch (err) {
      send.disabled = false;
      showToastError(err.message, "Correction non enregistrée");
      return;
    }
    form.replaceWith(el("p", "journal-card__sent", "✓ Correction enregistrée pour l'auto-apprentissage."));
    toggle.remove();
  });
  return form;
}

function logArticle(view) {
  const card = el("article", "journal-card");
  const head = el("div", "journal-card__head");
  const dot = el("span", `journal-card__dot journal-card__dot--${view.ok ? "ok" : "ko"}`);
  dot.setAttribute("role", "img");
  dot.setAttribute("aria-label", view.status);
  head.append(dot, el("span", "journal-card__intent", view.intent), el("span", "journal-card__date", view.date));

  const foot = el("div", "journal-card__foot");
  const toggle = button("btn journal-card__fix", "Corriger");
  toggle.setAttribute("aria-expanded", "false");
  toggle.setAttribute("aria-controls", `journal-feedback-${view.id}`);
  foot.append(el("span", "journal-card__meta", view.meta), toggle);

  card.append(head, line("Vous", view.query), line("Otis", view.reply), foot, feedbackForm(view, toggle));
  return card;
}
