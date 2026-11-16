// Feuille Sport : vues « Semaine » et « Mois · Année » (maquettes E-Sport et E-Sport-Annee).
import { fetchSportDashboardData, fetchSportSessionsData, fetchSportTodayData, fetchSportGamificationData } from "../../api.js";
import { state } from "../../config.js";
import {
  formatKm, formatThousands, healthBadge, weekGauge, periodLabel, isCurrentPeriod, previousRef, nextRef,
  sessionRow, chartBars, CHART_METRICS,
} from "../../sport_model.js";
import { el, button, periodNav, sessionLink, emptyNote, errorNote } from "./dom.js";

const COACH_STYLE = {
  alerte: { tone: "callout--danger", icon: "🩹" },
  vigilance: { tone: "callout--warn", icon: "⚠️" },
  info: { tone: "callout--accent", icon: "💬" },
};

const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

// Période affichée (null = période en cours), gardée tant que l'app est ouverte.
const view = { weekRef: null, periodRef: null };
let onOpenSession = () => {};
let onShowWeek = () => {};

export function initPeriodViews({ openSession, showWeek }) {
  onOpenSession = openSession;
  onShowWeek = showWeek;
}

function plural(count, word) {
  return `${count} ${word}${count > 1 ? "s" : ""}`;
}

// ---------- Semaine ----------

function coachCallout(tip) {
  const style = COACH_STYLE[tip.niveau] || COACH_STYLE.info;
  const box = el("div", `callout ${style.tone}`);
  box.setAttribute("role", "note");
  const icon = el("span", "callout__icon", style.icon);
  icon.setAttribute("aria-hidden", "true");
  const text = el("div");
  text.append(el("span", "callout__title", "Le mot du coach"), el("span", "callout__text", tip.message));
  box.append(icon, text);
  return box;
}

function weekCard(dash) {
  const totals = dash.totals || {};
  const card = el("div", "card");
  const head = el("div", "sport-card__head");
  const hero = el("div", "hero-number");
  hero.append(el("strong", null, formatKm(totals.distance_km || 0)), el("span", null, `km · ${plural(totals.nb_seances || 0, "séance")}`));
  head.append(hero);
  const badge = healthBadge(dash.alerte_securite);
  if (badge) {
    const tones = { ok: "badge--success", warn: "badge--warn", danger: "badge--danger" };
    const chip = el("span", `badge ${tones[badge.tone]}`, badge.label);
    chip.title = dash.alerte_securite;
    head.append(chip);
  }
  card.append(head);

  const gauge = weekGauge(totals.km_effort, dash.plafond_km_effort);
  if (gauge) {
    const wrap = el("div");
    const bar = el("div", `progress${gauge.over ? " progress--warn" : ""}`);
    bar.setAttribute("role", "progressbar");
    bar.setAttribute("aria-valuenow", String(gauge.pct));
    bar.setAttribute("aria-valuemin", "0");
    bar.setAttribute("aria-valuemax", "100");
    bar.setAttribute("aria-label", "Charge de la semaine par rapport au plafond");
    const fill = el("span");
    fill.style.setProperty("--value", `${gauge.pct}%`);
    bar.append(fill);
    const legend = el("div", "progress__legend");
    legend.append(el("span", null, gauge.value), el("span", null, gauge.limit));
    wrap.append(bar, legend);
    card.append(wrap);
  }

  const stats = el("div", "stat-grid stat-grid--divided");
  [
    ["Allure", totals.allure_formatted ? totals.allure_formatted.replace(/^0/, "") : "—"],
    ["Dénivelé", `+${totals.denivele_d_plus || 0} m`],
    ["Charge RPE", formatThousands(totals.charge_rpe || 0)],
  ].forEach(([label, value]) => {
    const stat = el("div", "stat");
    stat.append(el("span", "stat__label", label), el("span", "stat__value", value));
    stats.append(stat);
  });
  card.append(stats);
  return card;
}

export async function renderWeek(container) {
  container.setAttribute("aria-busy", "true");
  try {
    const today = todayIso();
    const [dash, todayData] = await Promise.all([
      fetchSportDashboardData("week", view.weekRef),
      fetchSportTodayData().catch((err) => {
        console.warn("[Sport] Conseil du coach indisponible :", err);
        return null;
      }),
    ]);
    const { sessions } = await fetchSportSessionsData({
      order: "asc", limit: 50, date_from: dash.start_date, date_to: dash.end_date,
    });
    const current = isCurrentPeriod(dash, today);
    const label = periodLabel(dash);
    const blocks = [];
    if (current && todayData && todayData.coach_tip) blocks.push(coachCallout(todayData.coach_tip));
    blocks.push(periodNav({
      ...label,
      prevLabel: "Semaine précédente",
      nextLabel: "Semaine suivante",
      onPrev: () => { view.weekRef = previousRef(dash); renderWeek(container); },
      onNext: current ? null : () => { view.weekRef = nextRef(dash); renderWeek(container); },
    }));
    blocks.push(weekCard(dash));
    if (sessions.length) {
      sessions.forEach((session) => {
        const link = sessionLink(sessionRow(session));
        link.addEventListener("click", () => onOpenSession(session, link));
        blocks.push(link);
      });
    } else {
      blocks.push(emptyNote("Aucune séance cette semaine."));
    }
    container.replaceChildren(...blocks);
  } catch (err) {
    console.error("[Sport] Vue Semaine indisponible :", err);
    container.replaceChildren(errorNote(`Semaine indisponible : ${err.message}`));
  } finally {
    container.removeAttribute("aria-busy");
  }
}

// ---------- Mois · Année ----------

function scaleRail(dash, container) {
  const rail = el("div", "seg seg--rail");
  rail.setAttribute("role", "tablist");
  rail.setAttribute("aria-label", "Échelle");
  const isMonth = dash.scale === "month";
  const monthBtn = button(null, isMonth ? dash.label.split(" ")[0] : "Mois");
  const yearBtn = button(null, dash.start_date.slice(0, 4));
  [[monthBtn, "month"], [yearBtn, "year"]].forEach(([btn, scale]) => {
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-selected", String(dash.scale === scale));
    btn.addEventListener("click", () => {
      if (dash.scale === scale) return;
      // Mois : celui de la date affichée (mois en cours pour l'année en cours) ; Année : celle du mois affiché.
      const today = todayIso();
      state.currentSportScale = scale;
      view.periodRef = scale === "month" && dash.end_date >= today && dash.start_date <= today ? null : dash.start_date;
      renderPeriod(container);
    });
  });
  rail.append(monthBtn, yearBtn);
  return rail;
}

function metricTile(label, value, metric, container, dash) {
  const tile = button("stat-tile stat");
  tile.setAttribute("aria-pressed", String(state.currentSportMetric === metric));
  tile.append(el("span", "stat__label", label), el("span", "stat__value", value));
  tile.addEventListener("click", () => {
    state.currentSportMetric = state.currentSportMetric === metric ? "volume" : metric;
    container.replaceChildren(...periodBlocks(dash, container, view.milestone));
  });
  return tile;
}

function chartCard(dash, container) {
  const metric = CHART_METRICS[state.currentSportMetric] ? state.currentSportMetric : "volume";
  const bars = chartBars(dash, todayIso(), metric);
  const card = el("div", "card sport-chart");
  const per = dash.scale === "year" ? "par mois · touche un mois" : "par semaine · touche une semaine";
  card.append(el("span", "sport-chart__title", `${CHART_METRICS[metric]} ${per}`));
  const grid = el("div", "bars");
  const axis = el("div", "bars__axis");
  bars.forEach((bar) => {
    const col = button("bars__col", null, `${bar.axis} : ${bar.value || "aucune donnée"}`);
    if (bar.current) col.setAttribute("aria-current", "true");
    col.append(el("span", "bars__val", bar.value));
    const fill = el("span", "bars__bar");
    fill.style.setProperty("--h", `${bar.pct}%`);
    col.append(fill);
    col.addEventListener("click", () => {
      if (bar.scale === "week") {
        view.weekRef = bar.ref;
        onShowWeek();
      } else {
        state.currentSportScale = "month";
        view.periodRef = bar.ref;
        renderPeriod(container);
      }
    });
    grid.append(col);
    axis.append(el("span", null, bar.axis));
  });
  card.append(grid, axis);
  return card;
}

function periodBlocks(dash, container, milestone) {
  const today = todayIso();
  const totals = dash.totals || {};
  const current = isCurrentPeriod(dash, today);
  const blocks = [periodNav({
    center: scaleRail(dash, container),
    prevLabel: dash.scale === "year" ? "Saison précédente" : "Mois précédent",
    nextLabel: dash.scale === "year" ? "Saison suivante" : "Mois suivant",
    onPrev: () => { view.periodRef = previousRef(dash); renderPeriod(container); },
    onNext: current ? null : () => { view.periodRef = nextRef(dash); renderPeriod(container); },
  })];
  const hero = el("div", "hero-number hero-number--xl");
  hero.append(el("strong", null, formatKm(totals.distance_km || 0)), el("span", null, `km · ${plural(totals.nb_seances || 0, "séance")}`));
  blocks.push(hero);
  const tiles = el("div", "stat-grid");
  tiles.append(
    metricTile("Allure moy.", totals.allure_formatted ? totals.allure_formatted.replace(/^0/, "") : "—", "allure", container, dash),
    metricTile(`km${"‑"}effort`, formatThousands(totals.km_effort || 0), "effort", container, dash),
    metricTile("Charge RPE", formatThousands(totals.charge_rpe || 0), "charge", container, dash),
  );
  blocks.push(tiles, chartCard(dash, container));
  if (milestone) blocks.push(el("p", "sport-milestone", milestone));
  return blocks;
}

export async function renderPeriod(container) {
  container.setAttribute("aria-busy", "true");
  try {
    const [dash, gamification] = await Promise.all([
      fetchSportDashboardData(state.currentSportScale, view.periodRef),
      fetchSportGamificationData().catch((err) => {
        console.warn("[Sport] Palier imminent indisponible :", err);
        return null;
      }),
    ]);
    const imminent = gamification && (gamification.imminent_milestones || [])[0];
    view.milestone = imminent ? `🎯 ${imminent.message}` : null;
    container.replaceChildren(...periodBlocks(dash, container, view.milestone));
  } catch (err) {
    console.error("[Sport] Vue Mois · Année indisponible :", err);
    container.replaceChildren(errorNote(`Statistiques indisponibles : ${err.message}`));
  } finally {
    container.removeAttribute("aria-busy");
  }
}
