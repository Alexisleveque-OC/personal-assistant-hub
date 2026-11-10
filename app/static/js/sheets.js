// Feuilles (sections qui montent du bas) et menu burger — refonte UX.
// Sans import : `createSheetManager` reçoit ses éléments et se teste sous Node ; `bindSheetInteractions`
// branche les gestes du navigateur (Échap, fond, glissé vers le bas).

const SWIPE_CLOSE_PX = 90;

export function createSheetManager({ getSheet, app, drawer, backdrop, burger }) {
  // Pile des feuilles ouvertes : [{ el, trigger }], la dernière est au-dessus.
  const stack = [];
  const listeners = [];
  let drawerTrigger = null;

  function requireSheet(id) {
    const el = getSheet(id);
    if (!el) throw new Error(`Feuille introuvable : « ${id} » (id attendu sur une <section class="sheet">).`);
    return el;
  }

  function notify() {
    const top = topSheetId();
    listeners.forEach((fn) => fn(top));
  }

  // Seule la feuille du dessus est interactive ; l'accueil est inerte dès qu'une feuille est ouverte.
  function syncLayers() {
    stack.forEach(({ el }, index) => { el.inert = index !== stack.length - 1; });
    const covered = stack.length > 0 || drawer.classList.contains("is-open");
    app.inert = covered;
    backdrop.classList.toggle("is-open", covered);
  }

  function hide(el) {
    el.classList.remove("is-open", "active");
    el.setAttribute("aria-hidden", "true");
    el.inert = true;
  }

  function topSheetId() {
    return stack.length ? stack[stack.length - 1].el.id : null;
  }

  // `active` : compatibilité avec les vues existantes (collage d'image) qui testent leur conteneur.
  function openSheet(id, trigger = null) {
    const el = requireSheet(id);
    if (drawer.classList.contains("is-open")) closeDrawer({ restoreFocus: false });
    el.classList.add("is-open", "active");
    el.setAttribute("aria-hidden", "false");
    stack.push({ el, trigger });
    syncLayers();
    el.focus();
    notify();
  }

  // Section ouverte depuis le menu ou une bulle : elle remplace les feuilles ouvertes au lieu de s'empiler.
  function openSection(id, trigger = null) {
    requireSheet(id);
    while (stack.length) hide(stack.pop().el);
    openSheet(id, trigger);
  }

  function closeTop() {
    const entry = stack.pop();
    if (!entry) return;
    hide(entry.el);
    syncLayers();
    if (entry.trigger && typeof entry.trigger.focus === "function") entry.trigger.focus();
    notify();
  }

  function closeAll() {
    if (!stack.length) return;
    const first = stack[0];
    while (stack.length) hide(stack.pop().el);
    syncLayers();
    if (first.trigger && typeof first.trigger.focus === "function") first.trigger.focus();
    notify();
  }

  function openDrawer(trigger = burger) {
    drawerTrigger = trigger;
    drawer.classList.add("is-open");
    drawer.setAttribute("aria-hidden", "false");
    drawer.inert = false;
    if (burger) burger.setAttribute("aria-expanded", "true");
    syncLayers();
    drawer.focus();
  }

  function closeDrawer({ restoreFocus = true } = {}) {
    if (!drawer.classList.contains("is-open")) return;
    drawer.classList.remove("is-open");
    drawer.setAttribute("aria-hidden", "true");
    drawer.inert = true;
    if (burger) burger.setAttribute("aria-expanded", "false");
    syncLayers();
    if (restoreFocus && drawerTrigger && typeof drawerTrigger.focus === "function") drawerTrigger.focus();
  }

  // Échap : le menu d'abord, sinon la feuille du dessus.
  function handleEscape() {
    if (drawer.classList.contains("is-open")) closeDrawer();
    else closeTop();
  }

  function onChange(fn) {
    listeners.push(fn);
  }

  return {
    openSheet, openSection, closeTop, closeAll, openDrawer, closeDrawer, handleEscape, onChange, topSheetId,
    isDrawerOpen: () => drawer.classList.contains("is-open"),
  };
}

// Gestes du navigateur : Échap, toucher du fond, croix (`data-sheet-close`), glissé vers le bas sur la poignée / l'en-tête.
export function bindSheetInteractions(manager, doc) {
  doc.addEventListener("keydown", (e) => {
    if (e.key === "Escape") manager.handleEscape();
  });

  doc.addEventListener("click", (e) => {
    if (e.target.closest(".sheet-backdrop")) {
      if (manager.isDrawerOpen()) manager.closeDrawer();
      else manager.closeTop();
      return;
    }
    if (e.target.closest("[data-sheet-close]")) manager.closeTop();
    else if (e.target.closest("[data-drawer-close]")) manager.closeDrawer();
  });

  doc.querySelectorAll(".sheet").forEach((sheet) => {
    const grips = sheet.querySelectorAll(".sheet__handle, .sheet__header");
    let startY = null;
    let delta = 0;

    grips.forEach((grip) => {
      grip.addEventListener("pointerdown", (e) => {
        if (e.target.closest("button, a, input, select, textarea")) return;
        startY = e.clientY;
        delta = 0;
        sheet.style.transition = "none";
        try { grip.setPointerCapture(e.pointerId); } catch (err) { /* pointeur déjà relâché */ }
      });
      grip.addEventListener("pointermove", (e) => {
        if (startY === null) return;
        delta = Math.max(0, e.clientY - startY);
        sheet.style.transform = `translateY(${delta}px)`;
      });
      const release = () => {
        if (startY === null) return;
        startY = null;
        sheet.style.transition = "";
        sheet.style.transform = "";
        if (delta > SWIPE_CLOSE_PX && manager.topSheetId() === sheet.id) manager.closeTop();
      };
      grip.addEventListener("pointerup", release);
      grip.addEventListener("pointercancel", release);
    });
  });
}
