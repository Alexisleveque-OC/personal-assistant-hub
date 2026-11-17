// Enregistrement du service worker de la PWA : mise à jour vérifiée à chaque démarrage, rechargement unique
// quand une nouvelle version prend la main.
export function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  let refreshing = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (!refreshing) {
      refreshing = true;
      window.location.reload();
    }
  });

  navigator.serviceWorker.register("/sw.js")
    .then((reg) => {
      console.log("[PWA] Service Worker registered");
      reg.update();
    })
    .catch((err) => console.warn("[PWA] Service Worker registration failed:", err));
}
