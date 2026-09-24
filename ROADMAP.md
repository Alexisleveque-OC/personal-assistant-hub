# Roadmap Feature : Interface Mobile & Entrées Vocales Android (`feat/android-voice-interface`)

> **Règle d'or (AGENTS.md) :**
> - Chaque étape doit être validée **manuellement et explicitement par l'utilisateur** avant de passer à la suivante.
> - La suite de tests automatisés (`pytest`) doit être à **100% au vert** à chaque étape.
> - Tout nouveau code de production est développé en **TDD Strict** (Phase Rouge $\rightarrow$ Phase Verte $\rightarrow$ Refactor).
> - À la fin de la feature, un **test d'intégration End-to-End (E2E)** valide le flux complet en conditions réelles sur smartphone.

---

## Vue d'ensemble des Étapes

| Étape | Description | Statut | Validation Utilisateur | Tests Automatisés |
| :--- | :--- | :---: | :---: | :---: |
| **Étape 1** | Sécurisation de l'API & Authentification par clé API (`X-API-Key`) | 🟢 Réalisé | ✅ Validé par l'utilisateur | ✅ 133/133 tests verts (TDD) |
| **Étape 2** | Adaptateur Webhook Mobile (Interopérabilité HTTP Shortcuts & Android) | 🟢 Réalisé | ✅ Validé par l'utilisateur | ✅ 141/141 tests verts (TDD) |
| **Étape 3** | Micro-Web App PWA Mobile embarquée (STT, TTS, Thèmes Botaniques, Cache) | 🟢 Réalisé | ✅ Validé par l'utilisateur | ✅ 160/160 tests verts (TDD) |
| **Étape 4** | Tunnel sécurisé distant (Cloudflare Tunnel) & Guide d'installation Android | 🟢 Réalisé | ✅ Validé par l'utilisateur | ✅ Script de tunnel & Guide smartphone |
| **Étape 5** | Test d'intégration End-to-End (E2E) en conditions réelles sur smartphone | 🟢 Réalisé | ✅ Validé par l'utilisateur | ✅ Tests E2E complets (`tests/test_e2e_mobile_voice_flow.py`) |

---

## Détail des Étapes

### 🟢 Étape 1 : Sécurisation de l'API & Authentification par clé API (`X-API-Key`)
* **Objectif :** Protéger l'API contre tout accès non autorisé lorsqu'elle sera exposée sur Internet via un tunnel HTTPS pour le smartphone.
* **Livrables & Réalisations :**
  * Variable d'environnement `API_KEY` ajoutée dans `app/config.py`.
  * Dépendance de sécurité `verify_api_key` implémentée dans `app/core/security.py` avec `APIKeyHeader(name="X-API-Key")`.
  * Mode permissif préservé si aucune clé n'est configurée (rétrocompatibilité totale).
  * Rejet strict `401 Unauthorized` si une clé est configurée et que le header est manquant ou invalide.
  * Protection appliquée sur les routes `/api/v1/*` de `app/main.py`.
  * Suite de tests TDD dans `tests/test_auth.py` : 5 nouveaux tests au vert.
  * **Suite complète : 133/133 tests au vert (100% de réussite).**

---

### 🟢 Étape 2 : Adaptateur Webhook Mobile (HTTP Shortcuts & Android)
* **Objectif :** Permettre à des applications Android de raccourcis/widgets (ex: *HTTP Shortcuts*, *Tasker*, widgets vocaux) d'envoyer des requêtes et de recevoir une réponse formatée pour la lecture vocale native (Android Text-to-Speech).
* **Livrables & Réalisations :**
  * Tolérance automatique sur le payload d'entrée (`query`, `text`, `message`, `prompt`, `q`) via `InteractionRequest.resolve_aliases` dans `app/core/models.py`.
  * Champs calculés `@computed_field` `speech` et `text` ajoutés sur `InteractionResponse` pour compatibilité directe avec les moteurs TTS Android.
  * Endpoint polyvalent `/api/v1/mobile/interact` implémenté en GET (query param `?text=...`) et POST.
  * Support du format de sortie en texte brut `text/plain` (via header `Accept: text/plain`) pour lecture vocale directe sans parsing JSON côté smartphone.
  * Traitement bienveillant des entrées vides sans crash HTTP 422.
  * Sécurité `X-API-Key` héritée et active sur les routes mobiles.
  * Suite de tests TDD dans `tests/test_mobile_webhook.py` : 8 nouveaux tests au vert.
  * **Suite complète : 141/141 tests au vert (100% de réussite).**

---

### 🟢 Étape 3 : Micro-Web App PWA Mobile embarquée (STT, TTS, Thèmes Botaniques, Cache)
* **Objectif :** Proposer une interface web mobile moderne servie directement par FastAPI (`/app`), installable comme une application native sur l'écran d'accueil Android (PWA).
* **Livrables & Réalisations :**
  * **Design mobile botanique & cocooning :** Système de design tokens centralisé avec sélecteur ☀️ / 🌙. Thème clair chaleureux lin/sauge et thème sombre contemporain ardoise/pétrole (anti-néon IA), sublimés par des fonds botaniques HD découpés sur-mesure.
  * **Mise en cache intelligente (Performance & Quotas) :** Cache mémoire avec TTL de 3 minutes pour les plannings et listes de courses, et invalidation immédiate à chaque écriture.
  * **Tri par rayon & Persistance des coches :** Tri ordonné selon la feuille Google Sheet, persistance locale des articles cochés lors du changement d'onglet ou de session.
  * **Bouton & Intentions vocales de fin de courses :** Intention `CHECK_SHOPPING_COMPLETION` (*« est-ce que j'ai bien tout ? »*, *« j'ai fini mes courses »*) et bouton 🏁 alertant vocalement et visuellement sur les articles manquants.
  * **Planning repas compact avec accordéon :** Vue synthétique semaine avec bouton dépliable pour révéler les ingrédients jour par jour.
  * **Reconnaissance vocale native (STT) & Synthèse vocale (TTS) :** Écoute micro avec animation d'égaliseur et lecture audio naturelle en français avec choix de voix.
  * **PWA Installable :** Fichier `manifest.json`, icône vectorielle SVG dédiée, et `sw.js` (Service Worker) pour la mise en cache applicative.
  * **Gestion clé API intégrée :** Modal de paramétrage de clé `X-API-Key` sauvegardée dans le `localStorage` du smartphone.
  * **Validation TDD :** Tests complets dans `tests/test_pwa_routes.py`, `tests/test_week_meals_and_api.py` et `tests/test_caching_and_completion.py`.
  * **Suite complète : 160/160 tests au vert (100% de réussite).**

---

### 🟢 Étape 4 : Tunnel sécurisé distant & Guide d'installation smartphone
* **Objectif :** Permettre au smartphone Android d'accéder à l'application partout (4G/5G, Wifi extérieur) via un tunnel HTTPS sécurisé sans ouverture de port box.
* **Livrables & Réalisations :**
  * **Lanceur de tunnel automatisé (`scripts/start_tunnel.ps1`) :** Vérification du statut Uvicorn, démarrage automatique de Cloudflare Tunnel (`cloudflared`), récupération dynamique de l'URL publique HTTPS (`https://*.trycloudflare.com/app`), génération automatique d'un QR Code scannable directement dans la console PowerShell, et détection de la clé d'API.
  * **Documentation & Guide d'installation complet (`docs/GUIDE_INSTALLATION_MOBILE.md`) :** Guide détaillé pas-à-pas pour l'installation PWA sous Android Chrome, enregistrement de la clé d'API dans l'application, utilisation vocale et de courses, et configuration optionnelle du widget HTTP Shortcuts.
  * **Nouveau Logo Botanique & PWA Icons :** Logo Monstera sur-mesure intégré et recadré à ~5% de marge respiratoire, génération de la suite complète d'icônes PWA (`icon-192.png`, `icon-512.png`, `icon-maskable-192.png`, `icon-maskable-512.png`, `apple-touch-icon.png`, `icon.svg`).
  * **Hygiène & Sécurité Git :** Exclusion des exécutables locaux dans `.gitignore` (`tools/`, `*.log`).
  * **Validation utilisateur :** Validé manuellement par l'utilisateur sur son smartphone Android.

---

### 🟢 Étape 5 : Test d'intégration End-to-End (E2E) en conditions réelles
* **Objectif :** Validation finale avec l'utilisateur sur son smartphone Android en direct et automatisation de la pérennité de la solution.
* **Livrables & Réalisations :**
  * **Scénarios validés en conditions réelles sur smartphone par l'utilisateur :**
    * Dictée vocale et synthèse TTS : *« Qu'est-ce qu'on mange ce soir ? »*
    * Ajout d'articles vocalement à la liste de courses.
    * Consultation de la liste avec tri par rayon et persistance des coches.
    * Changement d'ambiance ☀️ / 🌙 avec fonds botaniques.
    * Installation sur écran d'accueil avec nouvelle icône Monstera.
  * **Suite de tests automatisés E2E (`tests/test_e2e_mobile_voice_flow.py`) :**
    * Validation de l'intégrité du Manifest PWA, des icônes maskable/any et du Service Worker.
    * Validation des en-têtes anti-cache (`Cache-Control: no-cache, no-store`).
    * Validation de la barrière d'authentification (`X-API-Key`).
    * Validation du cycle complet de requêtes vocales (JSON et text/plain).
  * **Suite complète : 100% de tests au vert.**
