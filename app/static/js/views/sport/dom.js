// Feuille Sport : petits constructeurs DOM partagés par les vues (textes via textContent : jamais d'injection HTML).

export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

export function button(className, text, label) {
  const node = el("button", className, text);
  node.type = "button";
  if (label) node.setAttribute("aria-label", label);
  return node;
}

const SVG_NS = "http://www.w3.org/2000/svg";

// Chevron ‹ / › des navigations de période et des lignes de séance.
export function chevron(direction) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2.2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", direction === "left" ? "M15 6l-6 6 6 6" : "M9 6l6 6-6 6");
  svg.append(path);
  return svg;
}

// ‹ titre / sous-titre › ; `onNext` absent = flèche suivante désactivée (période en cours).
export function periodNav({ title, sub, center, prevLabel, nextLabel, onPrev, onNext }) {
  const nav = el("div", "period-nav");
  const prev = button("icon-btn", null, prevLabel);
  prev.append(chevron("left"));
  prev.addEventListener("click", onPrev);
  const next = button("icon-btn", null, nextLabel);
  next.append(chevron("right"));
  if (onNext) next.addEventListener("click", onNext);
  else next.disabled = true;
  let middle = center;
  if (!middle) {
    middle = el("div", "period-nav__label");
    middle.append(el("strong", null, title));
    if (sub) middle.append(el("span", null, sub));
  }
  nav.append(prev, middle, next);
  return nav;
}

// Ligne de séance cliquable (vue Semaine et vue Séances).
export function sessionLink(row, { detailed = false } = {}) {
  const link = button("card card--link sport-row");
  link.dataset.sessionId = String(row.id);
  link.append(el("span", "emoji sport-row__emoji", row.emoji));
  const text = el("span", "sport-row__text");
  text.append(el("strong", "sport-row__title", row.title));
  text.append(el("span", "sport-row__meta", detailed ? row.feel : row.summary));
  if (row.pain) text.append(el("span", "badge badge--danger sport-row__pain", row.pain));
  link.append(text);
  if (detailed && row.value) {
    const value = el("span", "sport-row__value", row.value);
    value.append(el("span", "sport-row__unit", ` ${row.unit}`));
    link.append(value);
  } else {
    const arrow = chevron("right");
    arrow.classList.add("sport-row__chevron");
    link.append(arrow);
  }
  return link;
}

export function emptyNote(text) {
  return el("p", "sport-empty muted", text);
}

export function errorNote(text) {
  return el("p", "sport-empty sport-empty--error", text);
}
