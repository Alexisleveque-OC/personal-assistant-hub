// Feuille Sport (refonte UX) : pilules Semaine · Mois-Année · Séances, barre d'actions
// (Dicter une séance / crayon / capture) ; détail, formulaire Séance et Trophées (icône 🏆) en feuilles empilées.
import { state } from "../../config.js";
import { initPeriodViews, renderWeek, renderPeriod } from "./period_view.js";
import { initSessionsList, renderSessionsList } from "./sessions_list_view.js";
import { initSessionDetail, openSessionDetail, refreshOpenSession, showUpdatedSession } from "./session_detail_view.js";
import { initSessionForm, openSessionForm } from "./session_form_view.js";
import { initTrophies, openTrophies, refreshOpenTrophies } from "./trophies_view.js";

const VIEWS = {
  week: { panel: "sport-week", render: renderWeek },
  period: { panel: "sport-period", render: renderPeriod },
  sessions: { panel: "sport-sessions-list", render: renderSessionsList },
};

const $ = (id) => document.getElementById(id);

export function showSportView(name) {
  const target = VIEWS[name] ? name : "week";
  state.currentSportSubview = target;
  Object.entries(VIEWS).forEach(([key, { panel }]) => { $(panel).hidden = key !== target; });
  document.querySelectorAll("#view-sport [data-sport-view]").forEach((tab) => {
    tab.setAttribute("aria-selected", String(tab.dataset.sportView === target));
  });
  return VIEWS[target].render($(VIEWS[target].panel));
}

// Ouverture de la feuille et réponse d'Otis : la vue affichée et la séance ouverte sont relues.
export function loadSport() {
  showSportView(state.currentSportSubview);
  refreshOpenSession();
  refreshOpenTrophies();
}

export { openTrophies };

export function initSportSheet(manager) {
  const reload = () => showSportView(state.currentSportSubview);
  const openSession = (session, trigger) => openSessionDetail(session, trigger);

  initPeriodViews({ openSession, showWeek: () => showSportView("week") });
  initSessionsList({ openSession });
  initSessionDetail(manager, {
    edit: (session, trigger, focusKey) => openSessionForm(session, trigger, { focusKey }),
    changed: reload,
  });
  initSessionForm(manager, {
    saved: (session, edited) => {
      if (edited && session) showUpdatedSession(session);
      reload();
    },
  });

  document.querySelectorAll("#view-sport [data-sport-view]").forEach((tab) => {
    tab.addEventListener("click", () => showSportView(tab.dataset.sportView));
  });
  initTrophies(manager);
  const trophies = $("btn-sport-trophies");
  trophies.addEventListener("click", () => openTrophies(trophies));

  const dictate = $("btn-sport-dictate");
  dictate.addEventListener("click", () => openSessionForm(null, dictate, { dictate: true }));
  const manual = $("btn-sport-new");
  manual.addEventListener("click", () => openSessionForm(null, manual));

  // Séance changée ailleurs (Otis dans la conversation, capture de montre) : la vue affichée se met à jour.
  window.addEventListener("sport-data-updated", () => {
    if ($("view-sport").classList.contains("is-open")) loadSport();
  });
}
