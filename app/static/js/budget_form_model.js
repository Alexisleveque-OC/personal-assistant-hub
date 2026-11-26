// Formulaire Dépense / Revenu de l'écran Budget (Phase 10, étape 7b) : données pures, sans import ni DOM (Node).
// Choix de catégorie : groupes de la liste pour une dépense, types du groupe Revenus pour un revenu (décision du 26/11).

export function emptyBudgetForm(today) {
  return { type: "depense", montant: "", categorie: "", libelle: "", date: today, swile: false, remboursement: false };
}

export function categoryChoices(overview, type) {
  if (type === "revenu") return [{ group: "Revenus", names: [...(overview.income_categories || [])] }];
  return (overview.groups || []).map((g) => ({ group: g.name, names: g.categories.map((c) => c.name) }));
}

// « 12,50 » ou « 12.5 » → 12.5 ; NaN si ce n'est pas un nombre.
function parseAmount(raw) {
  const text = String(raw).replace(/\s/g, "").replace(",", ".");
  return /^\d+(\.\d{1,2})?$/.test(text) ? Number(text) : NaN;
}

export function budgetFormToPayload(form, sessionId) {
  const montant = parseAmount(form.montant);
  const libelle = form.libelle.trim();
  const errors = [];
  if (!(montant > 0)) errors.push("Montant invalide (ex. 12,50).");
  if (!form.categorie) errors.push("Choisis une catégorie.");
  if (!libelle) errors.push("Écris un libellé.");
  if (!form.date) errors.push("Choisis une date.");
  if (errors.length) return { errors, payload: null };
  const expense = form.type === "depense";
  return {
    errors,
    payload: {
      type: form.type, montant, categorie: form.categorie, libelle, date: form.date,
      swile: expense && form.swile, remboursement: expense && form.remboursement, session_id: sessionId,
    },
  };
}
