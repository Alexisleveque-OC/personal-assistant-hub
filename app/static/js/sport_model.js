// Feuille Sport (refonte UX) : formats, contenu des vues Semaine · Mois-Année · Séances, détail et formulaire Séance.
// Sans import ni DOM (testé sous Node) ; le rendu est dans views/sport_*.js.

const DAYS_SHORT = ["Dim.", "Lun.", "Mar.", "Mer.", "Jeu.", "Ven.", "Sam."];
const MONTHS_SHORT = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
const MONTH_INITIALS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
const NB_HYPHEN = "‑"; // trait d'union insécable : « km‑effort » ne se coupe pas

// ---------- Dates (ISO AAAA-MM-JJ, jour local) ----------

function parseIso(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function toIso(day) {
  const mm = String(day.getMonth() + 1).padStart(2, "0");
  const dd = String(day.getDate()).padStart(2, "0");
  return `${day.getFullYear()}-${mm}-${dd}`;
}

export function shiftIso(iso, days) {
  const day = parseIso(iso);
  day.setDate(day.getDate() + days);
  return toIso(day);
}

// Semaine ISO 8601 (le jeudi de la semaine donne l'année).
export function isoWeekOf(iso) {
  const day = parseIso(iso);
  const thursday = new Date(day);
  thursday.setDate(day.getDate() + 3 - ((day.getDay() + 6) % 7));
  const firstThursday = new Date(thursday.getFullYear(), 0, 4);
  const week = 1 + Math.round(((thursday - firstThursday) / 86400000 - 3 + ((firstThursday.getDay() + 6) % 7)) / 7);
  return { week, year: thursday.getFullYear() };
}

// « Lun. 9 »
export function shortDay(iso) {
  const day = parseIso(iso);
  return `${DAYS_SHORT[day.getDay()]} ${day.getDate()}`;
}

// « Lun. 9 nov. »
export function longDay(iso) {
  const day = parseIso(iso);
  return `${shortDay(iso)} ${MONTHS_SHORT[day.getMonth()]}`;
}

// « 9 – 15 nov. », « 30 nov. – 6 déc. »
export function weekRange(startIso, endIso) {
  const start = parseIso(startIso);
  const end = parseIso(endIso);
  const endLabel = `${end.getDate()} ${MONTHS_SHORT[end.getMonth()]}`;
  if (start.getMonth() === end.getMonth()) return `${start.getDate()} – ${endLabel}`;
  return `${start.getDate()} ${MONTHS_SHORT[start.getMonth()]} – ${endLabel}`;
}

// ---------- Nombres ----------

// « 7,01 » (au plus deux décimales, virgule française)
export function formatKm(km) {
  return String(Math.round(Number(km) * 100) / 100).replace(".", ",");
}

// « 10 413 »
export function formatThousands(value) {
  return String(Math.round(Number(value) || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

// « 45:57 », « 1:02:03 » ; vide si inconnu
export function formatClock(seconds) {
  if (!seconds || seconds <= 0) return "";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

// Allure « 6:33 » (min/km) ; vide sans distance ni durée
function paceLabel(distanceKm, seconds) {
  if (!distanceKm || distanceKm <= 0 || !seconds || seconds <= 0) return "";
  const pace = Math.round(seconds / distanceKm);
  return `${Math.floor(pace / 60)}:${String(pace % 60).padStart(2, "0")}`;
}

// ---------- Types de séance ----------

// Types proposés pour créer ou modifier une séance (décision du 10/11) ; EF s'affiche « Endurance ».
export const TYPE_CHOICES = [
  { value: "EF", label: "Endurance" },
  { value: "Course", label: "Course" },
  { value: "Sortie Longue", label: "Sortie longue" },
  { value: "Vitesse", label: "Vitesse" },
  { value: "Fractionné", label: "Fractionné" },
  { value: "Renforcement", label: "Renforcement" },
];

const TYPE_EMOJI = {
  EF: "🏃", Course: "👟", "Sortie Longue": "🏔️", Vitesse: "🚀", "Fractionné": "⚡", Renforcement: "💪",
  Tempo: "🔥", "Récup": "🌱",
};

export function typeLabel(type) {
  const choice = TYPE_CHOICES.find((t) => t.value === type);
  return choice ? choice.label : (type || "Séance");
}

export function typeEmoji(type) {
  return TYPE_EMOJI[type] || "🏃";
}

const STATUS_LABEL = { "Réalisé": "Réalisée", "Prévu": "Prévue", "Annulé": "Annulée", Repos: "Repos" };

// ---------- Douleur ----------

const PAIN_WORDS = ["périostite", "periostite", "douleur", "mal ", "tibia", "mollet", "gêne", "gene", "tension"];

// Champs douleur en base ; tant qu'ils sont vides (historique), « Douleur ? » si les remarques en parlent.
export function painTag(session) {
  const level = session.douleur_intensite;
  if (level !== null && level !== undefined) {
    if (level <= 0) return null;
    const zone = (session.douleur_zone || "").trim();
    return zone ? `${zone} · ${level}/10` : `Douleur ${level}/10`;
  }
  const text = `${(session.remarques || "").toLowerCase()} `;
  return PAIN_WORDS.some((w) => text.includes(w)) ? "Douleur ?" : null;
}

// ---------- Vue Semaine ----------

// Badge issu de l'alerte de sécurité calculée par le serveur (🟢 / 🟡 / 🔴).
export function healthBadge(alerte) {
  if (!alerte) return null;
  if (alerte.startsWith("🔴")) return { label: "Risque", tone: "danger" };
  if (alerte.startsWith("🟡")) return { label: "Vigilance", tone: "warn" };
  return { label: "Saine", tone: "ok" };
}

// Jauge km-effort de la semaine / plafond (S-1 + 10 %) ; rien sans plafond.
export function weekGauge(kmEffort, plafond) {
  if (!plafond) return null;
  const done = Number(kmEffort) || 0;
  return {
    pct: Math.min(100, Math.round((done / plafond) * 100)),
    over: done > plafond,
    value: `${formatKm(done)} km${NB_HYPHEN}effort`,
    limit: `Plafond : ${formatKm(plafond)} km${NB_HYPHEN}eff`,
  };
}

export function periodLabel(dash) {
  if (dash.scale === "week") {
    return { title: `Semaine ${isoWeekOf(dash.start_date).week}`, sub: weekRange(dash.start_date, dash.end_date) };
  }
  if (dash.scale === "year") return { title: dash.start_date.slice(0, 4), sub: "" };
  return { title: dash.label, sub: "" };
}

// Période en cours (ou future) : pas de flèche « suivante ».
export function isCurrentPeriod(dash, todayIso) {
  return dash.end_date >= todayIso;
}

export const previousRef = (dash) => shiftIso(dash.start_date, -1);
export const nextRef = (dash) => shiftIso(dash.end_date, 1);

// ---------- Listes de séances ----------

export function sessionRow(session) {
  const planned = session.statut === "Prévu";
  const km = session.distance_km;
  const duration = formatClock(session.duree_secondes);
  const rpe = session.ressenti_rpe ? `RPE ${session.ressenti_rpe}` : "";
  const parts = planned
    ? ["Prévue", km ? `${formatKm(km)} km` : "", duration]
    : [km ? `${formatKm(km)} km` : "", duration, rpe];
  const feel = planned
    ? ["Prévue"]
    : [rpe, session.meteo_note ? `météo ${session.meteo_note}/10` : ""];
  let value = "";
  let unit = "";
  if (km) {
    value = formatKm(km);
    unit = "km";
  } else if (session.duree_secondes) {
    value = String(Math.round(session.duree_secondes / 60));
    unit = "min";
  }
  return {
    id: session.id,
    emoji: typeEmoji(session.type_seance),
    title: `${shortDay(session.date)} · ${typeLabel(session.type_seance)}`,
    summary: parts.filter(Boolean).join(" · "),
    feel: feel.filter(Boolean).join(" · "),
    value,
    unit,
    pain: painTag(session),
    planned,
  };
}

// Groupes par semaine ISO dans l'ordre reçu ; l'année est précisée quand ce n'est pas l'année en cours.
export function groupByWeek(sessions, currentYear) {
  const groups = [];
  sessions.forEach((session) => {
    const { week, year } = isoWeekOf(session.date);
    const key = `${year}-${week}`;
    let group = groups[groups.length - 1];
    if (!group || group.key !== key) {
      group = { key, label: year === currentYear ? `Semaine ${week}` : `Semaine ${week} · ${year}`, sessions: [] };
      groups.push(group);
    }
    group.sessions.push(session);
  });
  return groups.map(({ label, sessions: list }) => ({ label, sessions: list }));
}

// ---------- Vue Mois · Année : histogramme cliquable ----------

// Indicateur du graphique, choisi en touchant une tuile (retour d'usage du 03/11).
export const CHART_METRICS = {
  volume: "Volume (km)", effort: `km${NB_HYPHEN}effort`, allure: "Allure (min/km)", charge: "Charge RPE",
};

// Hauteur de barre et libellé : l'allure monte avec la vitesse mais s'affiche en min/km.
const METRIC_READERS = {
  volume: (p) => [p.distance_km || 0, String(Math.round(p.distance_km || 0))],
  effort: (p) => [p.km_effort || 0, String(Math.round(p.km_effort || 0))],
  allure: (p) => [p.vitesse_kmh || 0, p.vitesse_kmh ? paceLabel(p.vitesse_kmh, 3600) : ""],
  charge: (p) => [p.charge_rpe || 0, formatThousands(p.charge_rpe || 0)],
};

// Année : un mois par barre (jusqu'au mois en cours pour l'année en cours), touche = ce mois.
// Mois : une semaine par barre, touche = cette semaine (premier jour de la semaine dans le mois).
export function chartBars(dash, todayIso, metric = "volume") {
  const read = METRIC_READERS[metric] || METRIC_READERS.volume;
  let series = dash.series || [];
  const year = Number(dash.start_date.slice(0, 4));
  if (dash.scale === "year" && year === Number(todayIso.slice(0, 4))) {
    series = series.slice(0, Number(todayIso.slice(5, 7)));
  }
  const max = Math.max(0, ...series.map((p) => read(p)[0]));
  const monthStart = parseIso(dash.start_date);
  const firstMonday = shiftIso(dash.start_date, -((monthStart.getDay() + 6) % 7));
  return series.map((point, i) => {
    const [amount, value] = read(point);
    let ref;
    if (dash.scale === "year") {
      ref = `${year}-${String(i + 1).padStart(2, "0")}-01`;
    } else {
      const monday = shiftIso(firstMonday, 7 * i);
      ref = monday < dash.start_date ? dash.start_date : monday;
    }
    return {
      axis: dash.scale === "year" ? MONTH_INITIALS[i] : point.label,
      value,
      pct: max > 0 ? Math.round((amount / max) * 100) : 0,
      current: !!point.is_current,
      ref,
      scale: dash.scale === "year" ? "month" : "week",
    };
  });
}

// ---------- Détail d'une séance ----------

export function detailSubtitle(session) {
  const week = `Semaine ${isoWeekOf(session.date).week}`;
  return session.strava_id ? `${week} · import Strava` : week;
}

export function detailChips(session) {
  const chips = [
    { text: `${typeEmoji(session.type_seance)} ${typeLabel(session.type_seance)}`, tone: "warn" },
    { text: STATUS_LABEL[session.statut] || session.statut, tone: session.statut === "Réalisé" ? "ok" : "neutral" },
  ];
  const pain = painTag(session);
  if (pain) chips.push({ text: pain, tone: "danger" });
  return chips;
}

function tile(key, label, value, unit = "", editable = true) {
  const empty = value === "" || value === null || value === undefined;
  return { key, label, value: empty ? (editable ? "Ajouter" : "—") : String(value), unit: empty ? "" : unit, empty, editable };
}

export function detailTiles(s) {
  return [
    tile("distance", "Distance", s.distance_km ? formatKm(s.distance_km) : "", "km"),
    tile("duree", "Durée", formatClock(s.duree_secondes)),
    tile("allure", "Allure", paceLabel(s.distance_km, s.duree_secondes), "", false),
    tile("dplus", "Dénivelé", s.denivele_d_plus ? `+${s.denivele_d_plus}` : "", "m"),
    tile("rpe", "Ressenti", s.ressenti_rpe || "", "/10"),
    tile("meteo", "Météo", s.meteo_note || "", "/10"),
    tile("fcMoy", "FC moy.", s.fc_moyenne || ""),
    tile("fcMax", "FC max", s.fc_max || ""),
    tile("charge", "Charge", s.charge_rpe ? formatThousands(s.charge_rpe) : "", "", false),
  ];
}

// ---------- Formulaire Séance (créer / modifier) ----------

// Pastilles de note (RPE, météo, douleur) : un toucher choisit ; retoucher la note choisie l'efface si `allowEmpty`.
export function nextScaleValue(current, tapped, allowEmpty) {
  if (current === tapped) return allowEmpty ? null : current;
  return tapped;
}

const DEFAULT_PAIN_LEVEL = 5;

export function emptyForm(todayIso) {
  return {
    id: null, date: todayIso, type: "EF", statut: "Réalisé", distance: "", dplus: "",
    h: "", m: "", s: "", rpe: null, meteo: null, fcMoy: "", fcMax: "",
    remarques: "", programme: "", pain: false, painLevel: DEFAULT_PAIN_LEVEL, painZone: "", hadPain: false,
  };
}

function splitDuration(seconds) {
  if (!seconds || seconds <= 0) return { h: "", m: "", s: "" };
  return {
    h: String(Math.floor(seconds / 3600)),
    m: String(Math.floor((seconds % 3600) / 60)),
    s: String(Math.floor(seconds % 60)),
  };
}

export function sessionToForm(session) {
  const hadPain = (session.douleur_intensite || 0) > 0;
  return {
    id: session.id,
    date: session.date,
    type: session.type_seance,
    statut: session.statut === "Prévu" ? "Prévu" : "Réalisé",
    distance: session.distance_km ? formatKm(session.distance_km) : "",
    dplus: session.denivele_d_plus ? String(session.denivele_d_plus) : "",
    ...splitDuration(session.duree_secondes),
    rpe: session.ressenti_rpe || null,
    meteo: session.meteo_note || null,
    fcMoy: session.fc_moyenne ? String(session.fc_moyenne) : "",
    fcMax: session.fc_max ? String(session.fc_max) : "",
    remarques: session.remarques || "",
    programme: session.programme || "",
    pain: hadPain,
    painLevel: hadPain ? session.douleur_intensite : DEFAULT_PAIN_LEVEL,
    painZone: hadPain ? (session.douleur_zone || "") : "",
    hadPain,
  };
}

// Brouillon de dictée (route /sport/session/draft) : seuls les champs compris par Otis remplacent le formulaire.
export function applyDraft(form, draft) {
  const next = { ...form };
  if (draft.date) next.date = draft.date;
  if (draft.type_seance) next.type = draft.type_seance;
  if (draft.statut === "Prévu" || draft.statut === "Réalisé") next.statut = draft.statut;
  if (draft.distance_km !== undefined && draft.distance_km !== null) next.distance = formatKm(draft.distance_km);
  if (draft.denivele_d_plus !== undefined && draft.denivele_d_plus !== null) next.dplus = String(draft.denivele_d_plus);
  if (draft.duree_secondes) Object.assign(next, splitDuration(draft.duree_secondes));
  if (draft.ressenti_rpe) next.rpe = draft.ressenti_rpe;
  if (draft.meteo_note) next.meteo = draft.meteo_note;
  if (draft.fc_moyenne) next.fcMoy = String(draft.fc_moyenne);
  if (draft.fc_max) next.fcMax = String(draft.fc_max);
  if (draft.remarques) next.remarques = draft.remarques;
  if (draft.douleur_intensite !== undefined && draft.douleur_intensite !== null) {
    next.pain = draft.douleur_intensite > 0;
    if (next.pain) next.painLevel = draft.douleur_intensite;
  }
  if (draft.douleur_zone) next.painZone = draft.douleur_zone;
  return next;
}

function parseDecimal(text) {
  const clean = String(text).trim().replace(",", ".");
  if (clean === "") return null;
  return /^\d+(\.\d+)?$/.test(clean) ? Number(clean) : NaN;
}

function parseInteger(text) {
  const clean = String(text).trim();
  if (clean === "") return null;
  return /^\d+$/.test(clean) ? Number(clean) : NaN;
}

function formDuration(form) {
  const [h, m, s] = [form.h, form.m, form.s].map(parseInteger);
  if (h === null && m === null && s === null) return null;
  if ([h, m, s].some(Number.isNaN) || (m || 0) > 59 || (s || 0) > 59) return NaN;
  return (h || 0) * 3600 + (m || 0) * 60 + (s || 0);
}

export function formPace(form) {
  const distance = parseDecimal(form.distance);
  const seconds = formDuration(form);
  const pace = paceLabel(Number.isNaN(distance) ? null : distance, Number.isNaN(seconds) ? null : seconds);
  return pace ? `Allure calculée : ${pace} /km` : "";
}

// Charge utile de POST /sport/session ou PATCH /sport/session/id/{id} ; les valeurs non saisies ne sont pas envoyées.
export function formToPayload(form) {
  const errors = [];
  const payload = {};
  if (!form.date) errors.push("Date : choisis le jour de la séance.");
  else payload.date = form.date;
  payload.type_seance = form.type;
  payload.statut = form.statut;

  const distance = parseDecimal(form.distance);
  if (Number.isNaN(distance)) errors.push("Distance : nombre attendu (ex. 7,01).");
  else if (distance !== null) payload.distance_km = distance;

  const dplus = parseInteger(form.dplus);
  if (Number.isNaN(dplus)) errors.push("Dénivelé : nombre entier de mètres attendu.");
  else if (dplus !== null) payload.denivele_d_plus = dplus;

  const duration = formDuration(form);
  if (Number.isNaN(duration)) errors.push("Durée : minutes et secondes de 0 à 59.");
  else if (duration !== null) payload.duree_secondes = duration;

  if (form.rpe) payload.ressenti_rpe = form.rpe;
  if (form.meteo) payload.meteo_note = form.meteo;

  [["fcMoy", "fc_moyenne", "FC moyenne"], ["fcMax", "fc_max", "FC max"]].forEach(([key, field, label]) => {
    const value = parseInteger(form[key]);
    if (value === null) return;
    if (Number.isNaN(value) || value < 30 || value > 250) errors.push(`${label} : entre 30 et 250 bpm.`);
    else payload[field] = value;
  });

  payload.remarques = form.remarques.trim();
  payload.programme = form.programme.trim();

  if (form.pain) {
    payload.douleur_intensite = form.painLevel;
    payload.douleur_zone = form.painZone.trim();
  } else if (form.hadPain) {
    // Case décochée sur une séance douloureuse : 0 = aucune douleur (le serveur ignore les valeurs nulles).
    payload.douleur_intensite = 0;
    payload.douleur_zone = "";
  }
  return { errors, payload };
}
