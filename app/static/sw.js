const CACHE_NAME = "pah-pwa-cache-v33";
const ASSETS_TO_CACHE = [
  "/app",
  "/static/style.css",
  "/static/styles/hub.css",
  "/static/styles/app.css",
  "/static/styles/legacy-bridge.css",
  "/static/app.js",
  "/static/js/config.js",
  "/static/js/ui_shell.js",
  "/static/js/sheets.js",
  "/static/js/home_model.js",
  "/static/js/audio_focus.js",
  "/static/js/offline_outbox.js",
  "/static/js/api.js",
  "/static/js/toast.js",
  "/static/js/speech.js",
  "/static/js/voice_diag_log.js",
  "/static/js/wake_word_vosk.js",
  "/static/js/vosk_capture_worklet.js",
  "/static/js/screenshot_import.js",
  "/static/js/views/chat_view.js",
  "/static/js/views/home_view.js",
  "/static/js/views/second_brain_view.js",
  "/static/js/views/shopping_view.js",
  "/static/js/views/tasks_view.js",
  "/static/js/views/meals_view.js",
  "/static/js/views/sport_view.js",
  "/static/manifest.json",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/icon-maskable-192.png",
  "/static/icons/icon-maskable-512.png",
  "/static/icons/apple-touch-icon.png",
  "/static/icons/icon.svg"
];

// Installation du Service Worker
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      // `reload` : jamais une copie périmée du cache HTTP du navigateur dans le précache.
      return cache.addAll(ASSETS_TO_CACHE.map((url) => new Request(url, { cache: "reload" })));
    }).then(() => self.skipWaiting())
  );
});

// Activation et nettoyage des anciens caches
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Interception des requêtes réseau
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Pour les appels API dynamiques (/api/v1/*), stratégie Network-Only ou Network-First sans mise en cache statique
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(event.request).catch(() => {
        return new Response(
          JSON.stringify({
            success: false,
            spoken_response: "Vous êtes actuellement hors connexion. Veuillez vérifier votre réseau.",
            data: {}
          }),
          { status: 503, headers: { "Content-Type": "application/json" } }
        );
      })
    );
    return;
  }

  // Modèle Vosk (~42 Mo) : réseau direct, le worker Vosk le conserve déjà dans IndexedDB (pas de double stockage)
  if (url.pathname.startsWith("/vosk/")) {
    return;
  }

  // Pour les fichiers JS de logique (views, config, api, speech) : Network-First pour actualisation immédiate
  if (url.pathname.startsWith("/static/js/") || url.pathname.startsWith("/static/app.js")) {
    event.respondWith(
      // `no-cache` : revalide auprès du serveur au lieu d'une copie heuristiquement « fraîche » du cache HTTP.
      fetch(event.request, { cache: "no-cache" })
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseToCache = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseToCache));
          }
          return networkResponse;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Pour les assets de l'application (HTML, CSS, JS, icônes) : Stale-While-Revalidate
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      const fetchPromise = fetch(event.request, { cache: "no-cache" }).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200 && event.request.method === "GET") {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      }).catch(() => cachedResponse);

      return cachedResponse || fetchPromise;
    })
  );
});
