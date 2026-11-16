// Feuille Trophées (refonte UX, maquette E-Trophees) empilée sur Sport : compteur, palier imminent 🎯,
// derniers exploits, records perso, trophées par onglet (légendaires repliés), équivalences insolites.
import { fetchSportGamificationData } from "../../api.js";
import {
  TROPHY_TABS, trophiesForTab, trophyOverview, imminentMilestone, exploits, recordTile, equivalence,
} from "../../trophies_model.js";
import { el, button } from "./dom.js";

export const TROPHIES_SHEET_ID = "view-sport-trophies";

let manager = null;
let data = null; // dernière synthèse reçue
let currentTab = TROPHY_TABS[0].key;
const legendaryOpen = new Set(); // onglets dont les légendaires sont dépliés

const body = () => document.getElementById("trophies-body");
const todayIso = () => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
};

function progressBar(pct, extraClass = "") {
  const bar = el("div", `progress ${extraClass}`.trim());
  bar.setAttribute("role", "progressbar");
  bar.setAttribute("aria-valuemin", "0");
  bar.setAttribute("aria-valuemax", "100");
  bar.setAttribute("aria-valuenow", String(pct));
  const fill = el("span");
  fill.style.setProperty("--value", `${pct}%`);
  bar.append(fill);
  return bar;
}

function sectionBlock(title, ...children) {
  const block = el("div", "trophies__section");
  block.append(el("span", "section-label", title), ...children);
  return block;
}

function overviewCard() {
  const { unlocked, total, pct } = trophyOverview(data);
  const card = el("div", "card trophies__overview");
  const head = el("div", "trophies__count");
  const count = el("span", "trophies__count-value", String(unlocked));
  count.append(el("span", "trophies__count-total", ` / ${total}`));
  head.append(count, el("span", "trophies__count-pct", `${pct} %`));
  const main = el("div", "trophies__overview-main");
  main.append(head, progressBar(pct));
  card.append(el("span", "emoji trophies__overview-emoji", "🏆"), main);
  card.setAttribute("aria-label", `${unlocked} trophées débloqués sur ${total}, ${pct} %`);
  return card;
}

function milestoneCard(milestone) {
  const card = el("div", "callout callout--warn trophies__milestone");
  const text = el("div", "trophies__milestone-text");
  text.append(el("span", "trophies__milestone-title", "Palier imminent"), el("strong", null, milestone.message),
    progressBar(milestone.pct, "progress--sm progress--warn"));
  card.append(el("span", "emoji trophies__milestone-emoji", "🎯"), text);
  return card;
}

function trophyCard(card) {
  const node = el("div", `trophy ${card.unlocked ? "is-unlocked" : "is-locked"}${card.justUnlocked ? " just-unlocked" : ""}`);
  node.dataset.tier = card.tier;
  node.dataset.trophyId = card.id;
  const top = el("div", "trophy__top");
  const emoji = el("span", "emoji trophy__emoji", card.emoji);
  emoji.setAttribute("aria-hidden", "true");
  top.append(emoji, el("span", "trophy__tier", card.tierLabel));
  node.append(top, el("span", "trophy__name", card.name));
  if (card.desc) node.append(el("span", "trophy__desc", card.desc));
  if (card.unlocked) node.append(el("span", "trophy__done", card.doneLabel));
  if (card.progressPct !== null) node.append(progressBar(card.progressPct, "progress--sm"), el("span", "trophy__progress", card.progressLabel));
  return node;
}

function grid(cards) {
  const node = el("div", "trophy-grid");
  node.append(...cards.map(trophyCard));
  return node;
}

function tabsBlock() {
  const tabs = el("div", "chips trophies__tabs");
  tabs.setAttribute("role", "tablist");
  tabs.setAttribute("aria-label", "Catégorie de trophées");
  TROPHY_TABS.forEach((tab) => {
    const chip = button("chip", tab.label);
    chip.setAttribute("role", "tab");
    chip.setAttribute("aria-selected", String(tab.key === currentTab));
    chip.addEventListener("click", () => {
      currentTab = tab.key;
      render();
    });
    tabs.append(chip);
  });
  return tabs;
}

function trophiesBlock() {
  const { main, legendary } = trophiesForTab(data.badges, currentTab, todayIso());
  const blocks = [tabsBlock(), grid(main)];
  if (legendary.length) {
    if (legendaryOpen.has(currentTab)) {
      blocks.push(el("span", "section-label", "Légendaires 👑🪐"), grid(legendary));
    } else {
      const more = button("trophies__legendary", "Voir les légendaires 👑🪐");
      more.addEventListener("click", () => {
        legendaryOpen.add(currentTab);
        render();
      });
      blocks.push(more);
    }
  }
  return blocks;
}

function funRow(emoji, strong, small) {
  const row = el("div", "fun-row");
  const icon = el("span", "emoji", emoji);
  icon.setAttribute("aria-hidden", "true");
  const text = el("div");
  text.append(el("strong", null, strong), el("span", null, small));
  row.append(icon, text);
  return row;
}

function render() {
  if (!data) return;
  const blocks = [overviewCard()];
  const milestone = imminentMilestone(data);
  if (milestone) blocks.push(milestoneCard(milestone));

  const feats = exploits(data.announcements);
  if (feats.length) {
    blocks.push(sectionBlock("Derniers exploits", ...feats.map((f) => {
      const row = el("div", "card trophies__exploit");
      row.append(el("span", "emoji trophies__exploit-emoji", f.emoji), el("span", "trophies__exploit-text", f.text));
      return row;
    })));
  }

  const records = (data.personal_records || []).map(recordTile);
  if (records.length) {
    const tiles = el("div", "stat-grid trophies__records");
    records.forEach((r) => {
      const tile = el("div", "stat-tile stat");
      tile.append(el("span", "emoji trophies__record-emoji", r.emoji), el("span", "stat__value", r.value), el("span", "stat__label", r.label));
      tiles.append(tile);
    });
    blocks.push(sectionBlock("Records perso", tiles));
  }

  blocks.push(...trophiesBlock());

  const facts = (data.fun_facts || []).map(equivalence);
  if (facts.length) blocks.push(sectionBlock("Équivalences insolites", ...facts.map((f) => funRow(f.emoji, f.headline, f.detail))));

  body().replaceChildren(...blocks);
}

async function load() {
  if (!data) body().replaceChildren(el("p", "trophies__status", "Chargement des trophées…"));
  try {
    data = await fetchSportGamificationData();
    render();
  } catch (err) {
    console.error("[Trophées] Chargement impossible :", err);
    body().replaceChildren(el("p", "trophies__status", `Impossible de charger les trophées (${err.message}).`));
  }
}

export function openTrophies(trigger) {
  manager.openSheet(TROPHIES_SHEET_ID, trigger);
  return load();
}

// Après une réponse d'Otis ou une séance modifiée : la feuille ouverte se met à jour.
export function refreshOpenTrophies() {
  if (document.getElementById(TROPHIES_SHEET_ID).classList.contains("is-open")) load();
}

export function initTrophies(sheetManager) {
  manager = sheetManager;
  document.getElementById("btn-trophies-close").addEventListener("click", () => manager.closeAll());
}
