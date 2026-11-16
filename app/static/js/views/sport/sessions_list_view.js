// Feuille Sport : vue « Séances » (maquette E-Seances) — filtres type / statut, liste par semaine, 30 séances par page.
import { fetchSportSessionsData } from "../../api.js";
import { TYPE_CHOICES, sessionRow, groupByWeek } from "../../sport_model.js";
import { el, button, sessionLink, emptyNote, errorNote } from "./dom.js";

export const SESSIONS_PAGE_SIZE = 30;

// Types encore présents dans l'historique (Tempo, Récup) : filtrables même s'ils ne sont plus proposés.
const TYPE_FILTERS = [{ value: "", label: "Tous types" }, ...TYPE_CHOICES, { value: "Tempo", label: "Tempo" }, { value: "Récup", label: "Récup" }];
const STATUS_FILTERS = [{ value: "", label: "Toutes" }, { value: "Réalisé", label: "Réalisées" }, { value: "Prévu", label: "Prévues" }];

const filters = { type: "", statut: "", page: 0 };
let onOpenSession = () => {};

export function initSessionsList({ openSession }) {
  onOpenSession = openSession;
}

function filterSelect(label, options, key, container) {
  const select = el("select", "chip chip--select sport-filter");
  select.setAttribute("aria-label", label);
  options.forEach(({ value, label: text }) => {
    const option = el("option", null, text);
    option.value = value;
    option.selected = filters[key] === value;
    select.append(option);
  });
  select.addEventListener("change", () => {
    filters[key] = select.value;
    filters.page = 0; // un nouveau filtre repart des séances les plus récentes
    renderSessionsList(container);
  });
  return select;
}

function pagination(total, container) {
  const pages = Math.max(1, Math.ceil(total / SESSIONS_PAGE_SIZE));
  if (pages <= 1) return null;
  const nav = el("div", "sport-pages");
  const goTo = (page) => {
    filters.page = page;
    renderSessionsList(container).then(() => container.scrollIntoView({ block: "start" }));
  };
  const prev = button("btn", "Précédent");
  prev.disabled = filters.page === 0;
  prev.addEventListener("click", () => goTo(filters.page - 1));
  const next = button("btn", "Suivant");
  next.disabled = filters.page >= pages - 1;
  next.addEventListener("click", () => goTo(filters.page + 1));
  nav.append(prev, el("span", "muted", `Page ${filters.page + 1} / ${pages}`), next);
  return nav;
}

export async function renderSessionsList(container) {
  container.setAttribute("aria-busy", "true");
  try {
    const { sessions, total } = await fetchSportSessionsData({
      order: "desc",
      type_seance: filters.type,
      statut: filters.statut,
      limit: SESSIONS_PAGE_SIZE,
      offset: filters.page * SESSIONS_PAGE_SIZE,
    });
    const bar = el("div", "sport-filters");
    bar.append(
      filterSelect("Filtrer par type", TYPE_FILTERS, "type", container),
      filterSelect("Filtrer par statut", STATUS_FILTERS, "statut", container),
      el("span", "sport-filters__count", String(total)),
    );
    const blocks = [bar];
    if (!sessions.length) blocks.push(emptyNote("Aucune séance pour ces filtres."));
    groupByWeek(sessions, new Date().getFullYear()).forEach((group) => {
      blocks.push(el("span", "section-label", group.label));
      group.sessions.forEach((session) => {
        const link = sessionLink(sessionRow(session), { detailed: true });
        link.addEventListener("click", () => onOpenSession(session, link));
        blocks.push(link);
      });
    });
    const pages = pagination(total, container);
    if (pages) blocks.push(pages);
    container.replaceChildren(...blocks);
  } catch (err) {
    console.error("[Sport] Liste des séances indisponible :", err);
    container.replaceChildren(errorNote(`Séances indisponibles : ${err.message}`));
  } finally {
    container.removeAttribute("aria-busy");
  }
}
