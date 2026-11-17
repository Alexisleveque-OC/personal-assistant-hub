// Dates de la base SQLite (CURRENT_TIMESTAMP : UTC « AAAA-MM-JJ HH:MM:SS ») affichées à l'heure de Paris.
// Sans import ni DOM (testé sous Node) ; partagé par les feuilles Second cerveau et Journal & feedback.

const MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];

// Date de la base : UTC « AAAA-MM-JJ HH:MM:SS » (CURRENT_TIMESTAMP de SQLite) → « 5 nov. · 18:36 » à Paris.
function parisParts(date) {
  const parts = new Intl.DateTimeFormat("fr-FR", {
    timeZone: "Europe/Paris", year: "numeric", month: "numeric", day: "numeric",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(date);
  const get = (type) => Number(parts.find((p) => p.type === type).value);
  return { year: get("year"), month: get("month"), day: get("day"), hour: get("hour"), minute: get("minute") };
}

export function formatDbDate(createdAt, now) {
  if (!createdAt) return "";
  const date = new Date(`${String(createdAt).replace(" ", "T")}Z`);
  if (Number.isNaN(date.getTime())) return "";
  const p = parisParts(date);
  const year = p.year !== parisParts(now).year ? ` ${p.year}` : "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${p.day} ${MONTHS[p.month - 1]}${year} · ${pad(p.hour)}:${pad(p.minute)}`;
}
