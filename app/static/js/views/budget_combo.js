// Champ catégorie avec suggestions (combobox ARIA) des formulaires Budget : « cour » → Course (retour du 26/11).
// Le clavier du téléphone couvre le bas de l'écran : pendant la saisie, le formulaire réserve de la place en bas
// (classe `is-searching`) et la feuille défile pour placer `anchor` juste sous son en-tête.
import { matchCategories } from "../budget_form_model.js";
import { el } from "./sport/dom.js";

// `getChoices()` : catégories proposées ; `onPick(name)` : après le choix d'une suggestion.
export function bindCombo({ input, list, anchor, form, scroller, getChoices, onPick }) {
  const hide = () => {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
  };

  const lift = () => {
    scroller.scrollTop += anchor.getBoundingClientRect().top - scroller.getBoundingClientRect().top;
  };

  const show = () => {
    const options = matchCategories(getChoices(), input.value).map(({ name, group }, index) => {
      const option = el("li");
      option.id = `${list.id}-${index}`;
      option.setAttribute("role", "option");
      option.append(el("span", null, name), el("small", null, group));
      option.addEventListener("click", () => {
        input.value = name;
        input.dispatchEvent(new Event("change"));
        hide();
        onPick(name);
      });
      return option;
    });
    list.replaceChildren(...options);
    list.hidden = options.length === 0;
    input.setAttribute("aria-expanded", String(options.length > 0));
    if (options.length) lift();
  };

  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-controls", list.id);
  input.setAttribute("aria-expanded", "false");
  list.setAttribute("role", "listbox");
  input.addEventListener("input", show);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hide();
  });
  // Le toucher d'une suggestion ne doit pas d'abord fermer la liste (perte de focus du champ).
  list.addEventListener("pointerdown", (e) => e.preventDefault());
  input.addEventListener("focus", () => form.classList.add("is-searching"));
  input.addEventListener("blur", () => {
    hide();
    form.classList.remove("is-searching");
  });
  return { hide };
}
