// Coquille de l'app (refonte UX) : données pures, sans import ni DOM (testées sous Node).

// Sections de l'app : feuille qui l'affiche, placeholder de la barre de saisie et contexte transmis à Otis.
// L'accueil n'a pas de feuille. Les clés de contexte sont celles que lit le prompt de l'agent (`ui_context`).
export const SECTIONS = {
  accueil: { sheetId: null, title: "Accueil", placeholder: "Écrire à Otis…", context: "accueil" },
  courses: { sheetId: "view-shopping", title: "Courses", placeholder: "Ajouter un article…", context: "courses" },
  repas: { sheetId: "view-meals", title: "Repas", placeholder: "Planifier un repas…", context: "repas" },
  taches: { sheetId: "view-tasks", title: "Tâches", placeholder: "Nouvelle tâche…", context: "taches" },
  sport: { sheetId: "view-sport", title: "Sport", placeholder: "Écrire à Otis…", context: "sport" },
  second_cerveau: {
    sheetId: "view-second-brain", title: "Second cerveau", placeholder: "Noter une idée…", context: "second_cerveau",
  },
};

export function sectionForSheet(sheetId) {
  const found = Object.entries(SECTIONS).find(([, s]) => s.sheetId && s.sheetId === sheetId);
  return found ? found[0] : "accueil";
}

// Préférence enregistrée (« light » / « dark »), sinon celle du système.
export function resolveTheme(stored, prefersDark) {
  if (stored === "light" || stored === "dark") return stored;
  return prefersDark ? "dark" : "light";
}

// Raccourcis d'URL (?action=…) du manifeste et des widgets.
const ACTIONS = {
  shopping_list: { section: "courses", subview: null },
  meal_today: { section: "repas", subview: null },
  sport_today: { section: "sport", subview: null },
  sport_gamification: { section: "sport", subview: "gamification" },
  second_brain: { section: "second_cerveau", subview: null },
};

export function sectionForAction(action) {
  return (action && ACTIONS[action]) || null;
}

export function greetingFor(date) {
  return date.getHours() >= 18 ? "Bonsoir" : "Bonjour";
}

const WEEKDAYS = ["Dimanche", "Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"];
const MONTHS = [
  "janvier", "février", "mars", "avril", "mai", "juin",
  "juillet", "août", "septembre", "octobre", "novembre", "décembre",
];

export function formatLongDate(date) {
  return `${WEEKDAYS[date.getDay()]} ${date.getDate()} ${MONTHS[date.getMonth()]}`;
}
