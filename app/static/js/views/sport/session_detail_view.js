// Feuille Sport : détail d'une séance en feuille empilée (maquette E-Seance).
// La séance ouverte est transmise à Otis (`ui_session_id`) : « en fait c'était 48 minutes » corrige celle-là.
import { deleteSportSession, fetchSportSessionsData } from "../../api.js";
import { state } from "../../config.js";
import { showToastSuccess, showToastError, showToastInfo } from "../../toast.js";
import { longDay, detailSubtitle, detailChips, detailTiles } from "../../sport_model.js";
import { el, button } from "./dom.js";

export const DETAIL_SHEET_ID = "view-sport-session";

let manager = null;
let openSession = null; // séance affichée
let openSessionId = null;
let onEdit = () => {};
let onChanged = () => {};

const CHIP_TONES = { ok: "badge--ok", warn: "badge--warn", danger: "badge--danger", neutral: "" };

function render() {
  const s = openSession;
  document.getElementById("sport-session-title").textContent = longDay(s.date);
  document.getElementById("sport-session-sub").textContent = detailSubtitle(s);
  const sheet = document.getElementById(DETAIL_SHEET_ID);
  sheet.setAttribute("aria-label", `Séance du ${longDay(s.date)}`);

  const chips = el("div", "chips");
  detailChips(s).forEach((chip) => chips.append(el("span", `badge sport-chip ${CHIP_TONES[chip.tone] || ""}`, chip.text)));

  const tiles = el("div", "stat-grid");
  detailTiles(s).forEach((t) => {
    const tile = t.editable ? button(`stat-tile stat${t.empty ? " stat-tile--empty" : ""}`) : el("div", "stat-tile stat");
    tile.append(el("span", "stat__label", t.label));
    const value = el("span", t.empty ? "stat__value stat__value--empty" : "stat__value", t.value);
    if (t.unit) value.append(el("span", "stat__unit", ` ${t.unit}`));
    tile.append(value);
    if (t.editable) {
      tile.setAttribute("aria-label", `${t.label} : ${t.empty ? "ajouter" : `${t.value} ${t.unit}`.trim()}, modifier`);
      tile.addEventListener("click", () => onEdit(openSession, tile, t.key));
    }
    tiles.append(tile);
  });

  const blocks = [chips, tiles];
  [["Remarques & sensations", s.remarques], ["Programme", s.programme]].forEach(([label, text]) => {
    if (!text || !text.trim()) return;
    const card = el("div", "card sport-notes");
    card.append(el("span", "stat__label", label), el("p", "sport-notes__text", text));
    blocks.push(card);
  });
  document.getElementById("sport-session-body").replaceChildren(...blocks);
}

export function openSessionDetail(session, trigger) {
  openSession = session;
  openSessionId = session.id;
  render();
  manager.openSheet(DETAIL_SHEET_ID, trigger);
}

// Séance modifiée par le formulaire (réponse du PATCH) : affichée sans recharger.
export function showUpdatedSession(session) {
  if (!openSession || session.id !== openSessionId) return;
  openSession = session;
  render();
}

const isDetailOpen = () => document.getElementById(DETAIL_SHEET_ID).classList.contains("is-open");

// Après une réponse d'Otis : relit la séance ouverte (le serveur n'a pas de lecture par identifiant,
// on relit le jour de la séance). Introuvable à cette date : la feuille se ferme sur la liste rafraîchie.
export async function refreshOpenSession() {
  if (!openSession || !isDetailOpen()) return;
  const { date } = openSession;
  try {
    const { sessions } = await fetchSportSessionsData({ date_from: date, date_to: date, limit: 20 });
    const fresh = sessions.find((s) => s.id === openSessionId);
    if (fresh) {
      openSession = fresh;
      render();
    } else if (manager.topSheetId() === DETAIL_SHEET_ID) {
      manager.closeTop();
      showToastInfo("La séance n'est plus à cette date : la liste est à jour.", "Sport");
    }
  } catch (err) {
    console.warn("[Sport] Séance ouverte non relue :", err);
  }
}

async function deleteOpenSession() {
  if (!openSession) return;
  if (!window.confirm(`Supprimer la séance du ${longDay(openSession.date)} ? Cette action est définitive.`)) return;
  try {
    await deleteSportSession(openSessionId);
    showToastSuccess("Séance supprimée.", "Sport");
    manager.closeTop();
    onChanged();
  } catch (err) {
    showToastError(`Suppression impossible : ${err.message}`, "Sport");
  }
}

export function initSessionDetail(sheetManager, { edit, changed }) {
  manager = sheetManager;
  onEdit = edit;
  onChanged = changed;
  manager.onChange((topId) => {
    state.uiSessionId = topId === DETAIL_SHEET_ID ? openSessionId : null;
  });
  const editBtn = document.getElementById("btn-sport-session-edit");
  editBtn.addEventListener("click", () => onEdit(openSession, editBtn, null));
  document.getElementById("btn-sport-session-delete").addEventListener("click", deleteOpenSession);
}
