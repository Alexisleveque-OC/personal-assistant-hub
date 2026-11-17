// Feuille Sport : formulaire Séance unique, créer ou modifier (maquette E-Seance-Edit), en feuille empilée.
// « Dicte ta séance » : la dictée part vers la route brouillon (rien n'est enregistré), pré-remplit les champs,
// puis « OK » / « Enregistrer » enregistre (décision du 10/11).
import { createSportSession, patchSportSessionById, postSportSessionDraft } from "../../api.js";
import { captureOnce, stopCapture } from "../../mic_capture.js";
import { showToastSuccess, showToastError, showToastInfo } from "../../toast.js";
import {
  TYPE_CHOICES, typeLabel, emptyForm, sessionToForm, applyDraft, formToPayload, formPace, nextScaleValue,
} from "../../sport_model.js";
import { button } from "./dom.js";

export const FORM_SHEET_ID = "view-sport-form";

const HINT = "Otis remplit les champs, tu corriges ce qui cloche.";
const TEXT_FIELDS = {
  date: "sport-form-date", distance: "sport-form-distance", dplus: "sport-form-dplus",
  h: "sport-form-h", m: "sport-form-m", s: "sport-form-s", fcMoy: "sport-form-fc-moy", fcMax: "sport-form-fc-max",
  remarques: "sport-form-remarques", programme: "sport-form-programme", painZone: "sport-form-pain-zone",
};
// Tuile touchée dans le détail → champ qui reçoit le focus.
const FOCUS_FOR_TILE = {
  distance: "sport-form-distance", duree: "sport-form-m", dplus: "sport-form-dplus", rpe: "sport-form-rpe",
  meteo: "sport-form-meteo", fcMoy: "sport-form-fc-moy", fcMax: "sport-form-fc-max",
};

let manager = null;
let form = null; // état du formulaire (voir emptyForm dans sport_model.js)
let original = null; // séance modifiée (null = création)
let dictating = false; // capture « Dicte ta séance » en cours
let dictationToken = 0; // une dictée qui revient après fermeture du formulaire est ignorée
let saving = false;
let onSaved = () => {};

const $ = (id) => document.getElementById(id);

const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

// ---------- Rendu de l'état dans les champs ----------

function renderTypes() {
  const choices = [...TYPE_CHOICES];
  // Ancien type (Tempo, Récup) d'une séance modifiée : affiché pour rester sélectionné, jamais proposé ailleurs.
  if (!choices.some((t) => t.value === form.type)) choices.push({ value: form.type, label: typeLabel(form.type) });
  const chips = choices.map(({ value, label }) => {
    const chip = button("chip chip--accent", label);
    chip.dataset.type = value;
    chip.setAttribute("aria-pressed", String(form.type === value));
    chip.addEventListener("click", () => {
      form.type = value;
      $("sport-form-types").querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", String(c === chip)));
    });
    return chip;
  });
  $("sport-form-types").replaceChildren(...chips);
}

// Pastilles de note sur une rangée (retour du 16/11 : un curseur bougeait quand le pouce passait dessus
// en faisant défiler) ; un toucher qui glisse pour défiler n'est jamais un clic.
function renderScale(id, value) {
  const group = $(id);
  if (!group.childElementCount) {
    for (let n = Number(group.dataset.min); n <= Number(group.dataset.max); n += 1) {
      const pill = button("scale__pill", String(n));
      pill.setAttribute("role", "radio");
      pill.dataset.value = String(n);
      group.append(pill);
    }
  }
  group.querySelectorAll(".scale__pill").forEach((pill) => {
    pill.setAttribute("aria-checked", String(Number(pill.dataset.value) === value));
  });
  $(`${id}-value`).textContent = value === null || value === undefined ? "— / 10" : `${value} / 10`;
}

function renderStatus() {
  $("sport-form-status").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.statut === form.statut)));
}

function renderPain() {
  $("sport-form-pain").checked = form.pain;
  $("sport-form-pain-detail").hidden = !form.pain;
  renderScale("sport-form-pain-level", form.painLevel);
}

function render() {
  Object.entries(TEXT_FIELDS).forEach(([key, id]) => { $(id).value = form[key]; });
  renderTypes();
  renderStatus();
  renderScale("sport-form-rpe", form.rpe);
  renderScale("sport-form-meteo", form.meteo);
  renderPain();
  $("sport-form-pace").textContent = formPace(form);
  showErrors([]);
}

function readTextFields() {
  Object.entries(TEXT_FIELDS).forEach(([key, id]) => { form[key] = $(id).value; });
}

function showErrors(errors) {
  const box = $("sport-form-errors");
  box.hidden = !errors.length;
  box.textContent = errors.join(" ");
}

// ---------- Dictée ----------

function setDictationHint(text) {
  $("sport-form-dictation-hint").textContent = text;
}

async function handleDraft(blob, token) {
  if (token !== dictationToken) return; // formulaire fermé entre-temps
  const mic = $("btn-sport-form-dictate");
  mic.disabled = true;
  setDictationHint("Otis lit ta dictée…");
  try {
    const { draft, dropped } = await postSportSessionDraft(blob);
    if (token !== dictationToken) return;
    readTextFields();
    form = applyDraft(form, draft || {});
    render();
    setDictationHint("Vérifie les champs, puis OK pour enregistrer.");
    if (dropped && dropped.length) showToastInfo(`Non retenu : ${dropped.join(", ")}. Complète à la main.`, "Dictée");
  } catch (err) {
    setDictationHint(HINT);
    showToastError(err.message, "Dictée");
  } finally {
    mic.disabled = false;
  }
}

function startDictation() {
  const token = dictationToken;
  if (!captureOnce((blob) => handleDraft(blob, token))) {
    showToastInfo("Dictée indisponible ici : remplis le formulaire à la main.", "Dictée");
  }
}

function toggleDictation() {
  if (dictating) stopCapture();
  else startDictation();
}

// ---------- Ouverture / enregistrement ----------

// `session` null = nouvelle séance ; `dictate` lance l'écoute dès l'ouverture ; `focusKey` = tuile touchée.
export function openSessionForm(session, trigger, { dictate = false, focusKey = null } = {}) {
  original = session;
  form = session ? sessionToForm(session) : emptyForm(todayIso());
  dictationToken += 1;
  setDictationHint(HINT);
  render();
  $("sport-form-title").textContent = session ? "Modifier la séance" : "Séance";
  manager.openSheet(FORM_SHEET_ID, trigger);
  if (focusKey && FOCUS_FOR_TILE[focusKey]) $(FOCUS_FOR_TILE[focusKey]).focus();
  if (dictate) startDictation();
}

async function save(e) {
  e.preventDefault();
  if (saving) return;
  readTextFields();
  const { errors, payload } = formToPayload(form);
  showErrors(errors);
  if (errors.length) return;
  saving = true;
  document.querySelectorAll(`#${FORM_SHEET_ID} [type="submit"]`).forEach((b) => { b.disabled = true; });
  try {
    const res = original ? await patchSportSessionById(original.id, payload) : await createSportSession(payload);
    showToastSuccess(original ? "Séance modifiée." : "Séance enregistrée.", "Sport");
    manager.closeTop();
    onSaved(res.session, !!original);
  } catch (err) {
    showErrors([err.message]);
  } finally {
    saving = false;
    document.querySelectorAll(`#${FORM_SHEET_ID} [type="submit"]`).forEach((b) => { b.disabled = false; });
  }
}

function bindScale(id, key) {
  const group = $(id);
  const allowEmpty = group.dataset.allowEmpty === "true";
  group.addEventListener("click", (e) => {
    const pill = e.target.closest(".scale__pill");
    if (!pill) return;
    form[key] = nextScaleValue(form[key], Number(pill.dataset.value), allowEmpty);
    renderScale(id, form[key]);
  });
}

export function initSessionForm(sheetManager, { saved }) {
  manager = sheetManager;
  onSaved = saved;
  $("sport-form").addEventListener("submit", save);
  bindScale("sport-form-rpe", "rpe");
  bindScale("sport-form-meteo", "meteo");
  bindScale("sport-form-pain-level", "painLevel");
  $("sport-form-status").addEventListener("click", (e) => {
    const choice = e.target.closest("button[data-statut]");
    if (!choice) return;
    form.statut = choice.dataset.statut;
    renderStatus();
  });
  $("sport-form-pain").addEventListener("change", () => {
    readTextFields();
    form.pain = $("sport-form-pain").checked;
    renderPain();
  });
  ["sport-form-distance", "sport-form-h", "sport-form-m", "sport-form-s"].forEach((id) => {
    $(id).addEventListener("input", () => {
      readTextFields();
      $("sport-form-pace").textContent = formPace(form);
    });
  });
  $("btn-sport-form-dictate").addEventListener("click", toggleDictation);

  // Le bouton de l'encart suit l'écoute de la capture à usage unique.
  window.addEventListener("mic-listening", (e) => {
    if (!e.detail.oneShot) return;
    dictating = e.detail.listening;
    $("btn-sport-form-dictate").classList.toggle("is-listening", dictating);
  });
  // Formulaire fermé pendant l'écoute ou l'analyse : la dictée est abandonnée.
  manager.onChange((topId) => {
    if (topId === FORM_SHEET_ID) return;
    dictationToken += 1;
    if (dictating) stopCapture();
  });
}
