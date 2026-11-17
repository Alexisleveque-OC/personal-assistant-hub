// Feuille Repas (refonte UX, maquette E-Repas) : navigation de semaine, bande des 7 jours, cartes Midi / Soir,
// ingrédients de la semaine affichée. Sans import ni DOM (testé sous Node) ; le rendu est dans views/meals_view.js.
// Entrée : `week_plan` de GET /api/v1/meals/week?offset=N (onglet annuel « repas AAAA », samedi → vendredi),
// chaque jour avec `date` ISO (AAAA-MM-JJ) et `day_label` (« mar. 17 »). Dates comparées en texte ISO, sans fuseau.

const DAYS_LONG = ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"];
const DAYS_SHORT = ["Di", "Lu", "Ma", "Me", "Je", "Ve", "Sa"];
const MONTHS_LONG = [
  "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre",
];
const MONTHS_SHORT = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];

function utcDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

function dayDiff(fromIso, toIso) {
  return Math.round((utcDate(toIso) - utcDate(fromIso)) / 86400000);
}

// « 2026-11-17 » → { short: "Ma", num: "17", name: "mardi 17", full: "mardi 17 novembre" }
function describe(iso) {
  const d = utcDate(iso);
  const name = `${DAYS_LONG[d.getUTCDay()]} ${d.getUTCDate()}`;
  return {
    short: DAYS_SHORT[d.getUTCDay()],
    num: String(d.getUTCDate()).padStart(2, "0"),
    name,
    full: `${name} ${MONTHS_LONG[d.getUTCMonth()]}`,
  };
}

function stateOf(iso, todayIso) {
  if (iso < todayIso) return "past";
  return iso === todayIso ? "today" : "future";
}

export function weekStrip(week, todayIso) {
  return (week || []).map((d, index) => {
    const { short, num, name } = describe(d.date);
    return { index, short, num, name, state: stateOf(d.date, todayIso) };
  });
}

// Jour mis en avant à l'ouverture : aujourd'hui s'il est dans la semaine, sinon le premier jour (-1 si vide).
export function defaultDay(week, todayIso) {
  const list = week || [];
  if (!list.length) return -1;
  return Math.max(list.findIndex((d) => d.date === todayIso), 0);
}

const RELATIVE = { "-1": "Hier", "0": "Aujourd'hui", "1": "Demain" };

// Les 7 jours de la semaine affichée, en cartes Midi / Soir (retour du 17/11 : la semaine entière d'un coup).
export function dayCards(week, todayIso) {
  return (week || []).map((d, index) => {
    const name = describe(d.date).name;
    const relative = RELATIVE[String(dayDiff(todayIso, d.date))];
    const slots = [
      { key: "midi", label: "Midi", dish: d.lunch || null, ingredients: d.lunch_ingredients || [] },
      { key: "soir", label: "Soir", dish: d.dinner || null, ingredients: d.dinner_ingredients || [] },
    ];
    return { index, title: relative ? `${relative} · ${name}` : name, empty: slots.every((s) => !s.dish), slots };
  });
}

// En-tête ‹ › : « Cette semaine » / « Semaine prochaine »… et la plage « 14 – 20 nov. ».
export function weekNav(offset, startIso, endIso) {
  const titles = { "0": "Cette semaine", "1": "Semaine prochaine", "-1": "Semaine dernière" };
  const title = titles[String(offset)] || (offset > 0 ? `Dans ${offset} semaines` : `Il y a ${-offset} semaines`);
  const start = utcDate(startIso);
  const end = utcDate(endIso);
  const sameMonth = start.getUTCMonth() === end.getUTCMonth();
  const from = sameMonth ? `${start.getUTCDate()}` : `${start.getUTCDate()} ${MONTHS_SHORT[start.getUTCMonth()]}`;
  return { title, range: `${from} – ${end.getUTCDate()} ${MONTHS_SHORT[end.getUTCMonth()]}` };
}

// « Ajouter » sur un créneau vide : texte pré-rempli dans la barre (date complète : Otis l'écrit avec set_meal).
export function slotPrefill(week, index, key) {
  const label = key === "midi" ? "Midi" : "Soir";
  return `${label} ${describe(week[index].date).full} : `;
}

// « + Ajouter un plat » sur un créneau rempli : Otis complète le plat prévu (« Quiche lorraine + Coleslaw »).
export function addOnPrefill(week, index, key) {
  return `Ajouter au ${key === "midi" ? "midi" : "soir"} de ${describe(week[index].date).full} : `;
}

// « Demander une idée à Otis » : propositions seulement, rien n'est écrit sans confirmation.
export function ideaPrompt(week, index) {
  return `Propose-moi 2 ou 3 idées de repas pour ${describe(week[index].date).full} (midi et soir), `
    + "de préférence parmi mes recettes. N'écris rien dans le planning.";
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

// Bouton « Ingrédients de la semaine → courses » : masqué pour une semaine entièrement passée.
export function hasIngredientsButton(week, todayIso) {
  const list = week || [];
  return list.length > 0 && list[list.length - 1].date >= todayIso;
}

// Ingrédients des repas de la semaine affichée à partir d'aujourd'hui, sans doublon ; `listed` : déjà aux courses.
export function weekIngredients(week, shopping, todayIso) {
  const listed = shoppingKeys(shopping);
  const seen = new Set();
  const out = [];
  for (const d of (week || []).filter((day) => day.date >= todayIso)) {
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
