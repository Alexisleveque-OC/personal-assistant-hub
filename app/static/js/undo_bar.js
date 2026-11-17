// Barre « Annuler » de la conversation : dernière action réversible d'Otis, masquée après 8 secondes.
let undoTimeoutId = null;

export function showUndoToast(actionDescription, onUndoCallback) {
  const toast = document.getElementById("undo-toast");
  const textEl = document.getElementById("undo-toast-text");
  const btnUndo = document.getElementById("btn-undo-action");
  if (!toast || !btnUndo) return;

  if (undoTimeoutId) {
    clearTimeout(undoTimeoutId);
  }

  if (textEl) {
    textEl.textContent = actionDescription || "Dernière action réversible";
  }

  btnUndo.onclick = () => {
    hideUndoToast();
    if (onUndoCallback) onUndoCallback();
  };

  toast.hidden = false;

  // Masquage automatique après 8 secondes
  undoTimeoutId = setTimeout(() => {
    hideUndoToast();
  }, 8000);
}

export function hideUndoToast() {
  const toast = document.getElementById("undo-toast");
  if (!toast) return;
  if (undoTimeoutId) {
    clearTimeout(undoTimeoutId);
    undoTimeoutId = null;
  }
  toast.hidden = true;
}
