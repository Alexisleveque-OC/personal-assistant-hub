// Formulaires de l'écran Budget (Phase 10) : Dépense / Revenu (7b), Échéancier et Dépense multiple (7c), en onglets.
// Données pures, sans import ni DOM (testées sous Node).
// Choix de catégorie : groupes de la liste (dépense, échéancier, parts), types du groupe Revenus pour un revenu.
// Champ texte avec suggestions (retour du 26/11 : liste déroulante trop longue) : sans accents ni casse.

const MAX_SUGGESTIONS = 5; // le clavier du téléphone couvre le bas de l'écran (retour du 26/11)

function normalizeName(text) {
  return String(text).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim().replace(/\s+/g, " ");
}

const emptyPart = () => ({ categorie: "", montant: "" });

// `montant` : montant (dépense, revenu) ou montant total (échéancier, dépense multiple).
export function emptyBudgetForm(today) {
  return {
    type: "depense", montant: "", categorie: "", libelle: "", date: today, swile: false, remboursement: false,
    nom: "", nbEcheances: "", moisDebut: today.slice(0, 7), commentaire: "",
    motCle: "", parts: [emptyPart(), emptyPart()],
  };
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

const cents = (amount) => Math.round(amount * 100);
const euros = (amount) => `${(cents(amount) / 100).toFixed(2).replace(/[.,]00$/, "").replace(".", ",")} €`;
const amountOrZero = (raw) => (Number.isNaN(parseAmount(raw)) ? 0 : parseAmount(raw));
const isBlankPart = (part) => !part.categorie.trim() && !String(part.montant).trim();

// Dépense multiple : total − somme des parts (négatif = parts trop élevées).
export function splitRemainder(form) {
  const allotted = form.parts.reduce((sum, part) => sum + amountOrZero(part.montant), 0);
  return cents(amountOrZero(form.montant) - allotted) / 100;
}

// « Mettre le reste ici » : la part `index` reçoit ce qui reste à répartir (nouveau formulaire).
export function fillRemainder(form, index) {
  const value = amountOrZero(form.parts[index].montant) + splitRemainder(form);
  const parts = form.parts.map((part, i) => (i === index
    ? { ...part, montant: value > 0 ? value.toFixed(2).replace(".", ",") : "" } : part));
  return { ...form, parts };
}

export function addPart(form) {
  return { ...form, parts: [...form.parts, emptyPart()] };
}

export function removePart(form, index) {
  return { ...form, parts: form.parts.filter((_, i) => i !== index) };
}

// Nom tapé en entier (« course ») → nom exact de la liste ; "" s'il n'y est pas.
export function resolveCategory(choices, text) {
  const q = normalizeName(text);
  const found = q && choices.flatMap((c) => c.names).find((name) => normalizeName(name) === q);
  return found ? found.trim() : "";
}

// « 12,50 » ou « 12.5 » → 12.5 ; NaN si ce n'est pas un nombre.
function parseAmount(raw) {
  const text = String(raw).replace(/\s/g, "").replace(",", ".");
  return /^\d+(\.\d{1,2})?$/.test(text) ? Number(text) : NaN;
}

function installmentPayload(form, sessionId, choices) {
  const montant = parseAmount(form.montant);
  const count = Number(String(form.nbEcheances).trim());
  const categorie = resolveCategory(choices, form.categorie);
  const errors = [];
  if (!form.nom.trim()) errors.push("Écris un nom (magasin ou achat).");
  if (!(montant > 0)) errors.push("Montant invalide (ex. 12,50).");
  if (!Number.isInteger(count) || count < 2) errors.push("Nombre d'échéances : 2 ou plus.");
  if (!form.categorie.trim()) errors.push("Choisis une catégorie.");
  else if (!categorie) errors.push("Choisis une catégorie dans la liste.");
  if (errors.length) return { errors, payload: null };
  return {
    errors,
    payload: {
      nom: form.nom.trim(), montant_total: montant, nb_echeances: count, categorie,
      mois_debut: form.moisDebut || null, commentaire: form.commentaire.trim(), session_id: sessionId,
    },
  };
}

function splitPayload(form, sessionId, choices) {
  const total = parseAmount(form.montant);
  const errors = [];
  if (!form.motCle.trim()) errors.push("Écris le mot-clé du relevé bancaire.");
  if (!(total > 0)) errors.push("Montant invalide (ex. 12,50).");
  const parts = [];
  form.parts.forEach((part, index) => {
    if (isBlankPart(part)) return;
    const categorie = resolveCategory(choices, part.categorie);
    const montant = parseAmount(part.montant);
    if (!categorie) errors.push(`Part ${index + 1} : choisis une catégorie dans la liste.`);
    if (!(montant > 0)) errors.push(`Part ${index + 1} : montant invalide.`);
    parts.push({ categorie, montant });
  });
  if (!parts.length) errors.push("Ajoute au moins une part.");
  else if (total > 0 && splitRemainder(form) !== 0) {
    const allotted = total - splitRemainder(form);
    const remainder = splitRemainder(form);
    errors.push(remainder > 0
      ? `Les parts font ${euros(allotted)} sur ${euros(total)} : il reste ${euros(remainder)} à répartir.`
      : `Les parts font ${euros(allotted)} sur ${euros(total)} : ${euros(-remainder)} de trop.`);
  }
  if (!form.date) errors.push("Choisis une date.");
  if (errors.length) return { errors, payload: null };
  return { errors, payload: { mot_cle: form.motCle.trim(), montant_total: total, parts, date: form.date, session_id: sessionId } };
}

// `choices` : catégories proposées (categoryChoices) ; une catégorie envoyée est toujours un nom de la liste.
export function budgetFormToPayload(form, sessionId, choices) {
  if (form.type === "echeancier") return installmentPayload(form, sessionId, choices);
  if (form.type === "multiple") return splitPayload(form, sessionId, choices);
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
