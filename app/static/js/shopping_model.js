// Feuille Courses (refonte UX) : listes, rayons, quantités et message de fin de courses.
// Sans import ni DOM (testé sous Node) ; le rendu est dans views/shopping_view.js.

// Ordre des rayons quand le classeur ne le donne pas (clés normalisées, cf. normRayon).
const DEFAULT_RAYONS_ORDER = {
  "fruits": 1,
  "legumes": 2,
  "plat prepare": 3,
  "viande": 4,
  "charcuterie": 5,
  "dessert": 6,
  "fromage/beurre/creme": 7,
  "apero": 8,
  "oeufs/farine/lait": 9,
  "petit dej + bio": 10,
  "produit du monde": 11,
  "epicerie": 12,
  "boisson": 13,
  "hygiene": 14,
  "pq + entretien": 15,
  "surgele": 16,
  "divers": 999,
};
const UNKNOWN_RAYON_ORDER = 900;
const MISC_RAYON = "Divers";

function normRayon(rayon) {
  return (rayon || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").trim();
}

// « endive x3 » → { label: "endive", qty: "x3" } : le suffixe de quantité devient une pastille.
// Le nom complet reste la clé de l'article (coches, synchronisation avec le classeur).
export function splitQuantity(name) {
  const match = /^(.*\S)\s+[x×]\s?(\d+)$/i.exec(name || "");
  if (!match) return { label: name, qty: null };
  return { label: match[1], qty: `x${match[2]}` };
}

// Listes « Cette semaine » et « En attente » sous une même forme { name, rayon, checked }.
// Cette semaine : coché dans le classeur ou sur ce téléphone (en attente de « J'ai fini »).
export function shoppingLists(data, storedChecked = []) {
  const local = new Set(storedChecked);
  const week = ((data && data.current_week_items) || []).map((it) => ({
    name: it.name,
    rayon: it.rayon || null,
    checked: Boolean(it.checked) || local.has(it.name),
  }));
  const waiting = ((data && data.waiting_list) || []).map((it) => ({
    name: it.item,
    rayon: it.rayon || null,
    checked: Boolean(it.is_bought),
  }));
  return { week, waiting };
}

// Groupes par rayon dans l'ordre du magasin (classeur, sinon ordre par défaut ; inconnus puis « Divers » à la fin).
export function groupByRayon(items, rayonsOrder) {
  const order = { ...DEFAULT_RAYONS_ORDER };
  Object.entries(rayonsOrder || {}).forEach(([rayon, rank]) => {
    order[normRayon(rayon)] = rank;
  });
  const rankOf = (rayon) => (order[normRayon(rayon)] !== undefined ? order[normRayon(rayon)] : UNKNOWN_RAYON_ORDER);

  const groups = new Map();
  items.forEach((it) => {
    const rayon = it.rayon || MISC_RAYON;
    if (!groups.has(rayon)) groups.set(rayon, []);
    const { label, qty } = splitQuantity(it.name);
    groups.get(rayon).push({ name: it.name, label, qty, checked: it.checked });
  });

  return [...groups.entries()]
    .sort(([a], [b]) => rankOf(a) - rankOf(b) || a.localeCompare(b))
    .map(([rayon, rows]) => ({ rayon, count: rows.length, items: rows }));
}

export function remainingNames(items) {
  return items.filter((it) => !it.checked).map((it) => it.name);
}

export function remainingCount(items) {
  return remainingNames(items).length;
}

// Coches « Cette semaine » gardées sur le téléphone jusqu'à « J'ai fini mes courses ».
export function toggleStoredCheck(stored, name, checked) {
  if (!checked) return stored.filter((it) => it !== name);
  return stored.includes(name) ? stored : [...stored, name];
}

// Bandeau (et phrase dite) après « J'ai fini mes courses ».
export function completionMessage(remaining, synced) {
  if (!remaining.length) {
    return {
      tone: "success",
      title: "🎉 Félicitations !",
      text: "Vous avez tout pris dans votre liste. Vos courses sont complètes !",
      items: [],
      synced,
      speech: "Félicitations, vous avez tout pris ! Vos courses sont complètes et enregistrées dans le Google Sheet.",
    };
  }
  const n = remaining.length;
  return {
    tone: "warn",
    title: `⚠️ Il vous reste encore ${n} article${n > 1 ? "s" : ""} à prendre`,
    text: "",
    items: remaining,
    synced,
    speech: `Attention, il vous reste encore ${n} article(s) à prendre : ${remaining.slice(0, 4).join(", ")}.`,
  };
}
