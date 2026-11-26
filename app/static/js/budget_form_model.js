// Formulaire Dépense / Revenu de l'écran Budget (Phase 10, étape 7b) : données pures, sans import ni DOM (Node).
// Choix de catégorie : groupes de la liste pour une dépense, types du groupe Revenus pour un revenu (décision du 26/11).
// Champ texte avec suggestions (retour du 26/11 : liste déroulante trop longue) : sans accents ni casse.

const MAX_SUGGESTIONS = 5; // le clavier du téléphone couvre le bas de l'écran (retour du 26/11)

function normalizeName(text) {
  return String(text).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim().replace(/\s+/g, " ");
}

export function emptyBudgetForm(today) {
  return { type: "depense", montant: "", categorie: "", libelle: "", date: today, swile: false, remboursement: false };
}

export function categoryChoices(overview, type) {
  if (type === "revenu") return [{ group: "Revenus", names: [...(overview.income_categories || [])] }];
  return (overview.groups || []).map((g) => ({ group: g.name, names: g.categories.map((c) => c.name) }));
}

// « cour » → [Course, Recours] : les noms qui commencent par le texte d'abord, puis ceux qui le contiennent.
export function matchCategories(choices, query) {
  const q = normalizeName(query);
  if (!q) return [];
  const all = choices.flatMap(({ group, names }) => names.map((name) => ({ name: name.trim(), group })));
  const starts = all.filter((c) => normalizeName(c.name).startsWith(q));
  const contains = all.filter((c) => !normalizeName(c.name).startsWith(q) && normalizeName(c.name).includes(q));
  return [...starts, ...contains].slice(0, MAX_SUGGESTIONS);
}

// Nom tapé en entier (« course ») → nom exact de la liste ; "" s'il n'y est pas.
function resolveCategory(choices, text) {
  const q = normalizeName(text);
  const found = q && choices.flatMap((c) => c.names).find((name) => normalizeName(name) === q);
  return found ? found.trim() : "";
}

// « 12,50 » ou « 12.5 » → 12.5 ; NaN si ce n'est pas un nombre.
function parseAmount(raw) {
  const text = String(raw).replace(/\s/g, "").replace(",", ".");
  return /^\d+(\.\d{1,2})?$/.test(text) ? Number(text) : NaN;
}

// `choices` : catégories proposées (categoryChoices) ; la catégorie envoyée est toujours un nom de la liste.
export function budgetFormToPayload(form, sessionId, choices) {
  const montant = parseAmount(form.montant);
  const libelle = form.libelle.trim();
  const categorie = resolveCategory(choices, form.categorie);
  const errors = [];
  if (!(montant > 0)) errors.push("Montant invalide (ex. 12,50).");
  if (!form.categorie.trim()) errors.push("Choisis une catégorie.");
  else if (!categorie) errors.push("Choisis une catégorie dans la liste.");
  if (!libelle) errors.push("Écris un libellé.");
  if (!form.date) errors.push("Choisis une date.");
  if (errors.length) return { errors, payload: null };
  const expense = form.type === "depense";
  return {
    errors,
    payload: {
      type: form.type, montant, categorie, libelle, date: form.date,
      swile: expense && form.swile, remboursement: expense && form.remboursement, session_id: sessionId,
    },
  };
}
