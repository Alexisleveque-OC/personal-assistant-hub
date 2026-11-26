// Relecture de l'import Swile (Phase 10, étape 8) : données pures, testées sous Node.
// Décisions du 26/11 : lignes à cocher (doublons décochés), catégorie pré-remplie et modifiable (types du groupe
// Revenus pour un crédit), solde « ancien → nouveau » coché par défaut.
import { formatEuros } from "./budget_model.js";
import { categoryChoices, resolveCategory } from "./budget_form_model.js";

const dayMonth = (iso) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;

// Réponse de /swile/analyze → état modifiable de l'écran.
export function swileState(review) {
  return {
    lines: review.lignes.map((line) => ({ ...line, categorie: line.categorie || "", checked: line.cochee })),
    balance: review.solde ? { ...review.solde, checked: true } : null,
    warnings: [...(review.avertissements || [])],
  };
}

export function swileLineTexts(line) {
  const amount = line.type === "credit" ? `+${formatEuros(line.montant)}` : formatEuros(line.montant);
  return {
    title: line.marchand,
    meta: `${dayMonth(line.date)} · ${amount}`,
    note: line.doublon || (line.type === "credit" ? "Crédit → Revenus" : ""),
  };
}

export function swileBalanceText(balance) {
  const before = balance.actuel === null || balance.actuel === undefined ? "vide" : formatEuros(balance.actuel);
  return `Reste Swile (${balance.mois}) : ${before} → ${formatEuros(balance.nouveau)}`;
}

export function swileImportLabel(state) {
  const count = state.lines.filter((line) => line.checked).length;
  const balance = Boolean(state.balance && state.balance.checked);
  if (!count) return balance ? "Importer le solde" : "Rien à importer";
  return `Importer ${count} ligne${count > 1 ? "s" : ""}${balance ? " et le solde" : ""}`;
}

// Catégories proposées pour une ligne : dépenses (groupes de la liste) ou types de revenu (crédit).
export function swileChoices(overview, line) {
  return categoryChoices(overview, line.type === "credit" ? "revenu" : "depense");
}

export function swileToPayload(state, sessionId, overview) {
  const errors = [];
  const lignes = [];
  state.lines.filter((line) => line.checked).forEach((line) => {
    const where = `${line.marchand} (${dayMonth(line.date)})`;
    const categorie = resolveCategory(swileChoices(overview, line), line.categorie);
    if (!line.categorie.trim()) errors.push(`${where} : choisis une catégorie.`);
    else if (!categorie) errors.push(`${where} : choisis une catégorie dans la liste.`);
    lignes.push({ type: line.type, date: line.date, montant: line.montant, marchand: line.marchand, categorie });
  });
  const solde = state.balance && state.balance.checked ? state.balance.nouveau : null;
  if (!lignes.length && solde === null) errors.push("Coche au moins une ligne ou le solde.");
  if (errors.length) return { errors, payload: null };
  return { errors, payload: { lignes, solde, session_id: sessionId } };
}
