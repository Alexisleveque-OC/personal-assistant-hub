// Feuille Repas (refonte UX, maquette E-Repas) : bande des 7 jours, cartes Midi / Soir, ingrédients de la semaine.
// Sans import ni DOM (testé sous Node) ; le rendu est dans views/meals_view.js.
// Entrée : `week_plan` de GET /api/v1/meals/week (feuille « Cette semaine », samedi → vendredi, `day_label` « mar. 17 »).

const DAYS = {
  "lun": ["Lu", "lundi"], "mar": ["Ma", "mardi"], "mer": ["Me", "mercredi"], "jeu": ["Je", "jeudi"],
  "ven": ["Ve", "vendredi"], "sam": ["Sa", "samedi"], "dim": ["Di", "dimanche"],
};

// « mar. 17 » → { short: "Ma", num: "17", name: "mardi 17" } ; un libellé inconnu est gardé tel quel.
function parseLabel(label) {
  const text = String(label || "").trim();
  const match = /^([a-zéû]+)\.?\s+(\d{1,2})\b/i.exec(text);
  const day = match && DAYS[match[1].toLowerCase().slice(0, 3)];
  if (!day) return { short: text, num: "", name: text };
  return { short: day[0], num: match[2].padStart(2, "0"), name: `${day[1]} ${Number(match[2])}` };
}

function todayIndex(week) {
  return (week || []).findIndex((d) => d.is_today);
}

export function weekStrip(week) {
  const today = todayIndex(week);
  return (week || []).map((d, index) => {
    const state = today < 0 || index > today ? "future" : index === today ? "today" : "past";
    return { index, ...parseLabel(d.day_label), state };
  });
}

// Jour sélectionné à l'ouverture : aujourd'hui, sinon le premier jour (-1 si la semaine est vide).
export function defaultDay(week) {
  const list = week || [];
  if (!list.length) return -1;
  return Math.max(todayIndex(list), 0);
}

const RELATIVE = { "-1": "Hier", "0": "Aujourd'hui", "1": "Demain" };

function card(week, index, today) {
  const d = week[index];
  const name = parseLabel(d.day_label).name;
  const relative = today >= 0 ? RELATIVE[String(index - today)] : undefined;
  const slots = [
    { key: "midi", label: "Midi", dish: d.lunch || null, ingredients: d.lunch_ingredients || [] },
    { key: "soir", label: "Soir", dish: d.dinner || null, ingredients: d.dinner_ingredients || [] },
  ];
  return { index, title: relative ? `${relative} · ${name}` : name, empty: slots.every((s) => !s.dish), slots };
}

// Le jour choisi puis le lendemain (décision du 17/11), dans la limite de la semaine.
export function dayCards(week, selected) {
  const list = week || [];
  const today = todayIndex(list);
  return [selected, selected + 1].filter((i) => i >= 0 && i < list.length).map((i) => card(list, i, today));
}

// « Ajouter » sur un créneau vide : texte pré-rempli dans la barre (Otis écrit le plat avec set_meal).
export function slotPrefill(week, index, key) {
  const label = key === "midi" ? "Midi" : "Soir";
  return `${label} ${parseLabel(week[index].day_label).name} : `;
}

// « Demander une idée à Otis » : propositions seulement, rien n'est écrit sans confirmation.
export function ideaPrompt(week, index) {
  const name = parseLabel(week[index].day_label).name;
  return `Propose-moi 2 ou 3 idées de repas pour ${name} (midi et soir), de préférence parmi mes recettes. `
    + "N'écris rien dans le planning.";
}

// Comparaison tolérante : casse, accents, suffixe de quantité « x2 », pluriel simple en s / x.
function itemKey(name) {
  const base = String(name || "")
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/\s*[x×]\s*\d+\s*$/, "")
    .trim();
  return base.split(/\s+/).map((w) => (w.length > 3 && /[sx]$/.test(w) ? w.slice(0, -1) : w)).join(" ");
}

function shoppingKeys(shopping) {
  const names = [
    ...((shopping && shopping.current_week_items) || []).map((i) => i.name),
    ...((shopping && shopping.waiting_list) || []).map((i) => i.item),
  ];
  return new Set(names.map(itemKey));
}

// Ingrédients des repas d'aujourd'hui à vendredi, sans doublon ; `listed` : déjà dans la liste de courses.
export function weekIngredients(week, shopping) {
  const list = week || [];
  const listed = shoppingKeys(shopping);
  const seen = new Set();
  const out = [];
  for (const d of list.slice(Math.max(todayIndex(list), 0))) {
    for (const name of [...(d.lunch_ingredients || []), ...(d.dinner_ingredients || [])]) {
      const key = itemKey(name);
      if (!key || seen.has(key)) continue;
      seen.add(key);
      out.push({ name, listed: listed.has(key) });
    }
  }
  return out;
}

// Message envoyé à Otis : il range par rayon, demande les rayons inconnus et rend l'ajout annulable.
export function ingredientsMessage(names) {
  return `Ajoute aux courses : ${names.join(", ")}.`;
}
